"""Food search and creation."""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from annos.models import Food

# pg_trgm's default similarity_threshold. Named here so the value the `%`
# operator uses is visible rather than an invisible database setting.
SIMILARITY_THRESHOLD = 0.3


@dataclass(frozen=True)
class ServingUnitView:
    name: str
    grams: Decimal


@dataclass(frozen=True)
class FoodCandidate:
    """A search hit. Per-100g macros plus serving units, so the client can work
    out grams before it logs anything."""

    id: int
    name: str
    name_fi: str | None
    source: str
    per_100g: dict[str, Decimal | None]
    serving_units: list[ServingUnitView] = field(default_factory=list)
    owned: bool = False


def candidate_payload(c: FoodCandidate) -> dict:
    """JSON-safe shape for a candidate, shared by both adapters.

    Lives here rather than in each adapter so the two surfaces cannot disagree.
    They did once: REST serialised Decimal as "218.00" while MCP emitted 218.0,
    which is exactly the drift parity is supposed to prevent. Floats are correct
    for both — these are nutrition figures, not money.
    """
    return {
        "id": c.id,
        "name": c.name,
        "name_fi": c.name_fi,
        "source": c.source,
        "owned": c.owned,
        "per_100g": {k: (float(v) if v is not None else None) for k, v in c.per_100g.items()},
        "serving_units": [{"name": u.name, "grams": float(u.grams)} for u in c.serving_units],
    }


def _to_candidate(food: Food, subject: str) -> FoodCandidate:
    return FoodCandidate(
        id=food.id,
        name=food.name,
        name_fi=food.name_fi,
        source=food.source,
        per_100g={
            "kcal": food.kcal,
            "protein_g": food.protein_g,
            "carbs_g": food.carbs_g,
            "fat_g": food.fat_g,
            "fiber_g": food.fiber_g,
        },
        serving_units=[ServingUnitView(name=u.name, grams=u.grams) for u in food.serving_units],
        owned=food.owner_id == subject,
    )


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

    Trigram matching handles typos and Finnish inflections ("rahka" ->
    "maitorahka") without embeddings. The client already supplies the semantic
    layer — it knows kvarkki is quark and resolves "something light with protein"
    into concrete queries before calling.
    """
    if not query.strip():
        return []

    score = func.greatest(
        func.similarity(Food.name, query),
        func.similarity(func.coalesce(Food.name_fi, ""), query),
    ).label("score")

    stmt = (
        select(Food)
        .where(
            or_(Food.owner_id.is_(None), Food.owner_id == subject),
            or_(Food.name.op("%")(query), Food.name_fi.op("%")(query)),
        )
        .order_by(score.desc(), Food.name.asc())
        .limit(limit)
    )

    result = await session.execute(stmt)
    return [_to_candidate(food, subject) for food in result.scalars().unique()]
