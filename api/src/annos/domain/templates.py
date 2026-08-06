"""Meal templates: favourites and recipes as one loggable unit.

A template stores foods and grams only, never macros — the snapshot happens
at log time (see meals.py), so "the usual breakfast" logged next month uses
that day's food definitions. `total_grams` makes a template a recipe: the
whole batch weighs this much, and logging takes a portion of it.

Saving to an existing name replaces the contents: favourites evolve, and the
name is the identity a user refers to ("save this as my breakfast").
"""

from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import foods as foods_domain
from annos.domain import language as language_domain
from annos.domain import profile as profile_domain
from annos.models import LANGUAGES, Food, MealTemplate, MealTemplateItem


class InvalidTemplate(Exception):
    """The template shape is wrong: empty name, no items, bad grams…"""


class TemplateNotFound(Exception):
    """No such template for this subject — same deliberate ambiguity as foods:
    revealing that an id exists but is someone else's would leak data."""

    def __init__(self, template_id: int) -> None:
        super().__init__(f"no such template: {template_id}")
        self.template_id = template_id


async def _validated_items(
    session: AsyncSession, *, subject: str, items: list[dict]
) -> list[MealTemplateItem]:
    """Resolve food ids the caller may see. No macro snapshot here — that is
    log time's job."""
    if not items:
        raise InvalidTemplate("a template needs at least one item")

    rows = []
    for item in items:
        unknown = set(item) - {"food_id", "grams"}
        if unknown:
            raise InvalidTemplate(f"unknown item fields: {', '.join(sorted(unknown))}")
        try:
            food_id = int(item["food_id"])
            grams = Decimal(str(item["grams"]))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise InvalidTemplate("each item needs a food_id and grams") from exc
        if grams <= 0:
            raise InvalidTemplate("grams must be positive")

        food = await session.scalar(
            select(Food).where(
                Food.id == food_id,
                or_(Food.owner_id.is_(None), Food.owner_id == subject),
            )
        )
        if food is None:
            raise InvalidTemplate(f"no such food: {food_id}")
        rows.append(MealTemplateItem(food_id=food_id, grams=grams))
    return rows


async def save_template(
    session: AsyncSession,
    *,
    subject: str,
    name: str,
    items: list[dict],
    total_grams: float | None = None,
) -> dict:
    """Save a favourite or recipe under a name; the same name replaces.

    Replacement rather than refusal because the name *is* the identity —
    "save this as my breakfast" said twice means the second version.
    """
    name = (name or "").strip()
    if not name:
        raise InvalidTemplate("a template needs a name")
    if total_grams is not None and total_grams <= 0:
        raise InvalidTemplate("total_grams must be positive")

    profile = await profile_domain.get_profile(session, subject=subject)
    rows = await _validated_items(session, subject=subject, items=items)

    template = await session.scalar(
        select(MealTemplate).where(MealTemplate.subject == subject, MealTemplate.name == name)
    )
    created = template is None
    if template is None:
        template = MealTemplate(subject=subject, name=name)
        session.add(template)
    template.total_grams = total_grams
    template.items = rows
    await session.commit()
    await session.refresh(template)

    return _saved_payload(template, profile.timezone, created=created)


async def get_template(session: AsyncSession, *, subject: str, template_id: int) -> MealTemplate:
    template = await session.scalar(
        select(MealTemplate).where(MealTemplate.id == template_id, MealTemplate.subject == subject)
    )
    if template is None:
        raise TemplateNotFound(template_id)
    return template


# What revise_template accepts — save_template's vocabulary, plus the name.
REVISABLE_TEMPLATE_FIELDS = frozenset({"name", "items", "total_grams"})


def _saved_payload(template: MealTemplate, tz: str, *, created: bool) -> dict:
    return {
        "template_id": template.id,
        "name": template.name,
        "total_grams": float(template.total_grams) if template.total_grams is not None else None,
        "created": created,
        "items": [{"food_id": item.food_id, "grams": float(item.grams)} for item in template.items],
        "server_time": servertime.echo(tz),
    }


async def revise_template(
    session: AsyncSession, *, subject: str, template_id: int, changes: dict
) -> dict:
    """Correct a template by id: rename it, restate its items, set or clear
    the recipe yield. Items replace the whole list, like revise_log."""
    unknown = set(changes) - REVISABLE_TEMPLATE_FIELDS
    if unknown:
        raise InvalidTemplate(f"not revisable: {', '.join(sorted(unknown))}")
    if not changes:
        raise InvalidTemplate("nothing to revise: changes is empty")

    profile = await profile_domain.get_profile(session, subject=subject)
    template = await get_template(session, subject=subject, template_id=template_id)

    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name:
            raise InvalidTemplate("a template needs a name")
        taken = await session.scalar(
            select(MealTemplate).where(
                MealTemplate.subject == subject,
                MealTemplate.name == name,
                MealTemplate.id != template_id,
            )
        )
        if taken is not None:
            raise InvalidTemplate(f"a template named {name!r} already exists")
        template.name = name
    if "total_grams" in changes:
        total_grams = changes["total_grams"]
        if total_grams is not None and total_grams <= 0:
            raise InvalidTemplate("total_grams must be positive")
        template.total_grams = total_grams
    if "items" in changes:
        template.items = await _validated_items(session, subject=subject, items=changes["items"])

    await session.commit()
    await session.refresh(template)
    return _saved_payload(template, profile.timezone, created=False)


async def delete_template(session: AsyncSession, *, subject: str, template_id: int) -> dict:
    """Erase a template for good. Logs made from it are untouched — they carry
    their own snapshots and never referenced the template."""
    profile = await profile_domain.get_profile(session, subject=subject)
    template = await get_template(session, subject=subject, template_id=template_id)
    await session.delete(template)
    await session.commit()
    return {
        "deleted_template_id": template_id,
        "server_time": servertime.echo(profile.timezone),
    }


async def list_templates(session: AsyncSession, *, subject: str) -> dict:
    """Every template this account owns, with items readable enough to act on:
    names in the reader's language and kcal from *current* food definitions
    (estimates for display — the log-time snapshot is still authoritative)."""
    profile = await profile_domain.get_profile(session, subject=subject)
    language = await foods_domain.reading_language(session, subject=subject)

    templates = (
        (
            await session.execute(
                select(MealTemplate)
                .where(MealTemplate.subject == subject)
                .order_by(MealTemplate.name)
            )
        )
        .scalars()
        .all()
    )

    food_ids = {item.food_id for template in templates for item in template.items}
    foods = {}
    if food_ids:
        rows = await session.execute(select(Food).where(Food.id.in_(food_ids)))
        foods = {food.id: food for food in rows.scalars()}

    def _item_payload(item: MealTemplateItem) -> dict:
        food = foods.get(item.food_id)
        name = (
            language_domain.resolve(
                {lang: getattr(food, f"name_{lang}") for lang in LANGUAGES}, language
            )[0]
            if food is not None
            else None
        )
        kcal_per_100g = float(food.kcal) if food is not None and food.kcal is not None else None
        return {
            "food_id": item.food_id,
            "name": name,
            "grams": float(item.grams),
            "kcal_per_100g": kcal_per_100g,
            "kcal": (
                round(kcal_per_100g * float(item.grams) / 100, 2)
                if kcal_per_100g is not None
                else None
            ),
        }

    def _template_payload(template: MealTemplate) -> dict:
        items = [_item_payload(item) for item in template.items]
        kcal_values = [item["kcal"] for item in items if item["kcal"] is not None]
        return {
            "template_id": template.id,
            "name": template.name,
            "total_grams": (
                float(template.total_grams) if template.total_grams is not None else None
            ),
            "kcal": round(sum(kcal_values), 2) if kcal_values else None,
            "use_count": template.use_count,
            "last_used_at": (
                template.last_used_at.isoformat() if template.last_used_at is not None else None
            ),
            "items": items,
        }

    return {
        "templates": [_template_payload(template) for template in templates],
        "language": language,
        "server_time": servertime.echo(profile.timezone),
    }
