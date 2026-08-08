"""The read views over meal logs: one day against its target, and the recent
days as context.

A daily_summary call with no date means *today, server-defined* — the client
asking "how am I doing?" can never be off by a day. The response is arithmetic
and facts: totals, the active phase's target, what remains. Whether the number
is good news is the client's judgment, fed by `profile_context`.

The day's type (training or rest) picks which of the phase's targets is in
force; it resolves in annos.domain.days — a manual mark wins, else a
non-planned exercise session that day derives training, else rest — and the
payload carries the source of the resolution, so a wrong-but-labelled
assumption beats a hidden one.

recent_meals is the memory a stateless client lacks: what the user has been
eating lately, so "the usual" and "same as Tuesday" resolve into food ids and
grams without interrogating the user.

In both views names resolve at read time in the reader's language; macros come
from the log-time snapshot.
"""

from datetime import date as date_type
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import body as body_domain
from annos.domain import days as days_domain
from annos.domain import exercise as exercise_domain
from annos.domain import language as language_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.models import LANGUAGES, ExerciseLog, Food, MealLog


def _parse_date(value: str | date_type | None, tz: str) -> date_type:
    if value is None:
        return date_type.fromisoformat(servertime.local_date(tz))
    if isinstance(value, date_type):
        return value
    try:
        return date_type.fromisoformat(value)
    except ValueError as exc:
        raise meals_domain.InvalidLog(f"not an ISO 8601 date: {value!r}") from exc


async def _food_map(session: AsyncSession, logs) -> dict[int, Food]:
    """The food rows behind a set of logs, for read-time name resolution.

    A food row is never deleted, but a missing one degrades to a null name
    rather than a failed read.
    """
    food_ids = {item.food_id for log in logs for item in log.items}
    if not food_ids:
        return {}
    rows = await session.execute(select(Food).where(Food.id.in_(food_ids)))
    return {food.id: food for food in rows.scalars()}


def _item_payload(item, foods: dict[int, Food], language: str) -> dict:
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
        "estimated": item.estimated,
        "kcal": meals_domain._portion(item.kcal, item.grams),
        "protein_g": meals_domain._portion(item.protein_g, item.grams),
        "carbs_g": meals_domain._portion(item.carbs_g, item.grams),
        "fat_g": meals_domain._portion(item.fat_g, item.grams),
        # Nullable like the snapshot: a food without a stated fiber value
        # prints nothing rather than a fabricated zero.
        "fiber_g": meals_domain._portion(item.fiber_g, item.grams),
    }


def _meal_payload(log: MealLog, foods: dict[int, Food], language: str) -> dict:
    return {
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
        "items": [_item_payload(item, foods, language) for item in log.items],
    }


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

    foods = await _food_map(session, logs)
    language = profile.language or language_domain.DEFAULT

    phase = await body_domain.active_phase(session, subject=subject, on=day)

    day_type, day_type_source = await days_domain.resolve_day_type(
        session, subject=subject, on=day, tz=tz
    )

    exercise_logs = (
        (
            await session.execute(
                select(ExerciseLog)
                .where(
                    ExerciseLog.subject == subject,
                    ExerciseLog.ts >= start,
                    ExerciseLog.ts < end,
                )
                .order_by(ExerciseLog.ts)
            )
        )
        .scalars()
        .all()
    )

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
        "meals": [_meal_payload(log, foods, language) for log in logs],
        # The day's sessions ride along like its meals, in full — sets and
        # activity included, so a client revising a session it didn't create
        # sees its current contents without a second call (the same reason
        # meals carry their items).
        "exercise": [exercise_domain.session_payload(ex) for ex in exercise_logs],
        "profile_context": {
            "dietary_prefs": profile.dietary_prefs,
            "coaching_notes": profile.coaching_notes,
        },
        "server_time": servertime.echo(tz),
    }


# Enough for "the usual" and "last week"; more than this is analytics, and the
# analytics views (weekly_review) aggregate rather than list.
MAX_RECENT_DAYS = 31


async def recent_meals(session: AsyncSession, *, subject: str, days: int = 7) -> dict:
    """The last days' meals, newest first — context, not analytics.

    The window is the last `days` calendar days in the profile timezone,
    today included, so `days=1` reads as "today" and the default week always
    contains one of each weekday — "same as Tuesday" is always resolvable.
    Every meal carries its local calendar date, its log_id (for revise_log /
    delete_log) and its items with food ids and grams (for re-logging).
    Planned entries ride along flagged, like in daily_summary.
    """
    try:
        days = int(days)
    except (TypeError, ValueError) as exc:
        raise meals_domain.InvalidLog(f"days must be a number, not {days!r}") from exc
    if not 1 <= days <= MAX_RECENT_DAYS:
        raise meals_domain.InvalidLog(f"days must be between 1 and {MAX_RECENT_DAYS}")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone

    today = date_type.fromisoformat(servertime.local_date(tz))
    first = today - timedelta(days=days - 1)
    start, _ = meals_domain._day_window(first.isoformat(), tz)
    _, end = meals_domain._day_window(today.isoformat(), tz)
    logs = (
        (
            await session.execute(
                select(MealLog)
                .where(MealLog.subject == subject, MealLog.ts >= start, MealLog.ts < end)
                .order_by(MealLog.ts.desc())
            )
        )
        .scalars()
        .all()
    )

    foods = await _food_map(session, logs)
    language = profile.language or language_domain.DEFAULT

    return {
        "days": days,
        "meals": [
            # Which calendar day a log belongs to is the profile timezone's
            # call, same as everywhere: a 00:30 snack is the new day's.
            {"date": servertime.local_date(tz, log.ts), **_meal_payload(log, foods, language)}
            for log in logs
        ],
        "language": language,
        "server_time": servertime.echo(tz),
    }
