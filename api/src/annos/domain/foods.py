"""Food search and presentation."""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from annos.domain import language as language_domain
from annos.models import LANGUAGES, Food, UserProfile

# pg_trgm's default similarity_threshold, recorded for the reader: the `%`
# operator's cutoff is a database GUC (set_limit / pg_trgm.similarity_threshold),
# not this constant. Informational only — changing it here changes nothing.
SIMILARITY_THRESHOLD = 0.3

# Upper bound on a search window, enforced in find_food so the MCP path (which
# passes limit through unchecked) can't request an unbounded result set.
MAX_SEARCH_LIMIT = 50


@dataclass(frozen=True)
class ServingUnitView:
    code: str
    grams: Decimal
    names: dict[str, str | None]


@dataclass(frozen=True)
class FoodCandidate:
    """A search hit. Per-100g macros plus serving units, so the client can work
    out grams before it logs anything."""

    id: int
    names: dict[str, str | None]
    source: str
    per_100g: dict[str, Decimal | None]
    serving_units: list[ServingUnitView] = field(default_factory=list)
    owned: bool = False


def candidate_payload(c: FoodCandidate, language: str) -> dict:
    """JSON-safe shape for a candidate, shared by both adapters.

    Lives here rather than in each adapter so the two surfaces cannot disagree.
    They did once: REST serialised Decimal as "218.00" while MCP emitted 218.0,
    which is exactly the drift parity is supposed to prevent. Floats are correct
    for both — these are nutrition figures, not money.

    One name goes out, not all three. A search returns ten of these and the MCP
    client pays for every token; `name_language` tells it what it got, and the
    full set is a `get_food` away if it ever needs them.
    """
    name, name_language = language_domain.resolve(c.names, language)
    return {
        "id": c.id,
        "name": name,
        "name_language": name_language,
        "source": c.source,
        "owned": c.owned,
        "per_100g": {k: (float(v) if v is not None else None) for k, v in c.per_100g.items()},
        "serving_units": [
            {
                "code": u.code,
                # An unknown code renders as itself — a food from a label photo
                # can carry a unit Fineli never defined.
                "name": language_domain.resolve(u.names, language)[0] or u.code,
                "grams": float(u.grams),
            }
            for u in c.serving_units
        ],
    }


def _to_candidate(food: Food, subject: str) -> FoodCandidate:
    return FoodCandidate(
        id=food.id,
        names={lang: getattr(food, f"name_{lang}") for lang in LANGUAGES},
        source=food.source,
        per_100g={
            "kcal": food.kcal,
            "protein_g": food.protein_g,
            "carbs_g": food.carbs_g,
            "fat_g": food.fat_g,
            "fiber_g": food.fiber_g,
        },
        serving_units=[
            ServingUnitView(
                code=u.unit_code,
                grams=u.grams,
                names=(
                    {lang: getattr(u.unit_type, f"name_{lang}") for lang in LANGUAGES}
                    if u.unit_type is not None
                    else {}
                ),
            )
            for u in food.serving_units
        ],
        owned=food.owner_id == subject,
    )


async def reading_language(session: AsyncSession, *, subject: str) -> str:
    """The caller's preferred language, or the default if they have no profile.

    Search is reachable before registration, so a missing row is ordinary here
    rather than an error.
    """
    preferred = await session.scalar(
        select(UserProfile.language).where(UserProfile.subject == subject)
    )
    return preferred or language_domain.DEFAULT


async def find_food(
    session: AsyncSession,
    *,
    subject: str,
    query: str,
    limit: int = 10,
) -> list[FoodCandidate]:
    """Trigram search over global foods plus the caller's own.

    Scoped deliberately: a user's label-photo food must never surface in another
    user's search. Global rows are the Fineli seed and verified entries
    (owner_id IS NULL).

    All three languages are searched whatever the caller reads in. Someone with
    Finnish set still types "banana", and Fineli's Swedish names are sometimes
    the most descriptive of the three. The client already supplies the semantic
    layer — it knows kvarkki is quark and resolves "something light with protein"
    into concrete queries before calling.

    Matching is substring OR trigram: whole-string similarity alone scores a
    short query too low against Fineli's long compound names ("melon" against
    "Meloni, verkkomeloni/cantaloupemeloni, kuorittu" never clears the
    threshold), so a plain substring hit always qualifies — the same GIN
    trigram index serves both. The trigram arm stays for typos and missing
    umlauts, which a substring can't forgive. Ranking is *word* similarity,
    so mid-typing the finished word outranks the compounds it starts:
    "hunaja" lists Hunaja above Hunajameloni.
    """
    query = query.strip()
    if not query:
        return []

    # Bound the window in the domain, not just at the REST edge: the MCP tool
    # passes limit straight through, so an unbounded value would otherwise be a
    # cheap way to ask for the whole table.
    limit = max(1, min(limit, MAX_SEARCH_LIMIT))

    name_columns = [getattr(Food, f"name_{lang}") for lang in LANGUAGES]

    # A literal % or _ in the query stays literal inside the LIKE pattern.
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like_pattern = f"%{escaped}%"

    score = func.greatest(
        *(func.word_similarity(query, func.coalesce(column, "")) for column in name_columns)
    ).label("score")

    stmt = (
        select(Food)
        .where(
            or_(Food.owner_id.is_(None), Food.owner_id == subject),
            or_(
                *(column.ilike(like_pattern, escape="\\") for column in name_columns),
                *(column.op("%")(query) for column in name_columns),
            ),
        )
        .order_by(score.desc(), *(column.asc() for column in name_columns))
        .limit(limit)
    )

    result = await session.execute(stmt)
    return [_to_candidate(food, subject) for food in result.scalars().unique()]
