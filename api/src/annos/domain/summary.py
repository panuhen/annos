"""The day view: what was eaten, against what target.

A call with no date means *today, server-defined* — the client asking "how am
I doing?" can never be off by a day. The response is arithmetic and facts:
totals, the active phase's target, what remains. Whether the number is good
news is the client's judgment, fed by `profile_context`.

The day's type (training or rest) picks which of the phase's targets is in
force; it resolves in annos.domain.days — a manual mark wins, an unmarked day
is rest until exercise logging exists — and the payload carries the source of
the resolution, so a wrong-but-labelled assumption beats a hidden one.
"""

from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import body as body_domain
from annos.domain import days as days_domain
from annos.domain import language as language_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.models import LANGUAGES, Food, MealLog


def _parse_date(value: str | date_type | None, tz: str) -> date_type:
    if value is None:
        return date_type.fromisoformat(servertime.local_date(tz))
    if isinstance(value, date_type):
        return value
    try:
        return date_type.fromisoformat(value)
    except ValueError as exc:
        raise meals_domain.InvalidLog(f"not an ISO 8601 date: {value!r}") from exc


async def daily_summary(
    session: AsyncSession, *, subject: str, date: str | date_type | None = None
) -> dict:
    """One call, the whole day: totals, target, remaining, and the day's logs.

    Each meal carries its items (name, source, grams, kcal): the day view has
    to list what was eaten, and a client revising a log needs to see its
    current contents without having logged it in the same conversation.
    Planned entries appear in the list but count toward no totals.
    """
    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone
    day = _parse_date(date, tz)

    totals = await meals_domain.day_totals(
        session, subject=subject, local_date=day.isoformat(), tz=tz
    )

    start, end = meals_domain._day_window(day.isoformat(), tz)
    logs = (
        (
            await session.execute(
                select(MealLog)
                .where(MealLog.subject == subject, MealLog.ts >= start, MealLog.ts < end)
                .order_by(MealLog.ts)
            )
        )
        .scalars()
        .all()
    )

    # Names resolve at read time in the reader's language; macros come from
    # the log-time snapshot. A food row is never deleted, but a missing one
    # degrades to a null name rather than a failed summary.
    food_ids = {item.food_id for log in logs for item in log.items}
    foods = {}
    if food_ids:
        rows = await session.execute(select(Food).where(Food.id.in_(food_ids)))
        foods = {food.id: food for food in rows.scalars()}
    language = profile.language or language_domain.DEFAULT

    def _item_payload(item) -> dict:
        food = foods.get(item.food_id)
        name = (
            language_domain.resolve(
                {lang: getattr(food, f"name_{lang}") for lang in LANGUAGES}, language
            )[0]
            if food is not None
            else None
        )
        return {
            "food_id": item.food_id,
            "name": name,
            "source": food.source if food is not None else None,
            "grams": float(item.grams),
            "kcal": meals_domain._portion(item.kcal, item.grams),
            "protein_g": meals_domain._portion(item.protein_g, item.grams),
            "carbs_g": meals_domain._portion(item.carbs_g, item.grams),
            "fat_g": meals_domain._portion(item.fat_g, item.grams),
        }

    phase = await body_domain.active_phase(session, subject=subject, on=day)

    day_type, day_type_source = await days_domain.resolve_day_type(session, subject=subject, on=day)

    if phase is not None:
        training = day_type == "training"
        kcal_target = phase.kcal_target_training if training else phase.kcal_target_rest
        protein_target = phase.protein_target_training if training else phase.protein_target_rest
        target = {
            "kind": phase.kind,
            "kcal": kcal_target,
            "protein_g": protein_target,
            "rate_kg_per_week": (
                float(phase.rate_target_kg_per_week)
                if phase.rate_target_kg_per_week is not None
                else None
            ),
        }
        remaining = {
            "kcal": round(kcal_target - totals["kcal"], 2),
            "protein_g": round(protein_target - totals["protein_g"], 2),
        }
    else:
        target = None
        remaining = None

    return {
        "date": day.isoformat(),
        "day_type": day_type,
        "day_type_source": day_type_source,
        "totals": totals,
        "target": target,
        "remaining": remaining,
        "meals": [
            {
                "log_id": log.id,
                "ts": log.ts.isoformat(),
                "meal": log.meal,
                "planned": log.planned,
                "notes": log.notes,
                "kcal": round(
                    sum(
                        float(item.kcal) * float(item.grams) / 100
                        for item in log.items
                        if item.kcal is not None
                    ),
                    2,
                ),
                "items": [_item_payload(item) for item in log.items],
            }
            for log in logs
        ],
        "profile_context": {
            "dietary_prefs": profile.dietary_prefs,
            "coaching_notes": profile.coaching_notes,
        },
        "server_time": servertime.echo(tz),
    }
