"""Meal logging: the core loop.

Time rules (see the Time handling note): the server owns time. `ts` defaults
to now(); a client passes one only when the user stated a time, and a naive
timestamp is read in the profile timezone, because "yesterday at noon" means
noon where the user lives. Which calendar day a log counts toward is decided
at read time by the profile timezone — a 00:30 snack lands on the new day.

Macros are snapshotted per item at log time, per-100g. Food definitions
change; history must not. A grams-only revision rescales from the snapshot; a
food swap re-snapshots from today's definition, because a correction means
"what I actually ate", not "what the food used to be".
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import profile as profile_domain
from annos.models import INPUT_MODES, MEALS, Food, MealLog, MealLogItem

# What revise_log accepts. Item edits replace the whole list — "the one-sentence
# correction path" re-states the meal rather than diffing it.
REVISABLE = frozenset({"ts", "meal", "planned", "notes", "items"})

MACRO_FIELDS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


class UnknownFood(Exception):
    """The food id does not exist, or belongs privately to someone else.

    One exception for both cases on purpose: revealing that a food id exists
    but is someone else's would leak what other users have created.
    """

    def __init__(self, food_id: int) -> None:
        super().__init__(f"no such food: {food_id}")
        self.food_id = food_id


class LogNotFound(Exception):
    """No such log for this subject. Same deliberate ambiguity as UnknownFood."""


class InvalidLog(Exception):
    """The request shape is wrong: empty items, bad meal, bad grams…"""


def _parse_ts(value: str | datetime | None, tz: str) -> datetime | None:
    """A stated time, UTC. Naive input is read in the profile timezone."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise InvalidLog(f"not an ISO 8601 timestamp: {value!r}") from exc
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(tz))
    return value


def _day_window(local_date_iso: str, tz: str) -> tuple[datetime, datetime]:
    """The UTC instants where a calendar day starts and ends in `tz`."""
    zone = ZoneInfo(tz)
    day = datetime.fromisoformat(local_date_iso).date()
    start = datetime.combine(day, time.min, tzinfo=zone)
    return start, start + timedelta(days=1)


async def _snapshot_items(
    session: AsyncSession,
    *,
    subject: str,
    items: list[dict],
    keep: dict[int, dict] | None = None,
) -> list[MealLogItem]:
    """Resolve food ids the caller may see and copy their per-100g macros.

    `keep` maps food_id to an existing snapshot to reuse. A revision that only
    changes grams must rescale from what was true at log time, not silently
    absorb whatever the food row says today.
    """
    if not items:
        raise InvalidLog("a meal needs at least one item")

    rows = []
    for item in items:
        unknown = set(item) - {"food_id", "grams"}
        if unknown:
            raise InvalidLog(f"unknown item fields: {', '.join(sorted(unknown))}")
        try:
            food_id = int(item["food_id"])
            grams = Decimal(str(item["grams"]))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise InvalidLog("each item needs a food_id and grams") from exc
        if grams <= 0:
            raise InvalidLog("grams must be positive")

        snapshot = (keep or {}).get(food_id)
        if snapshot is None:
            food = await session.scalar(
                select(Food).where(
                    Food.id == food_id,
                    or_(Food.owner_id.is_(None), Food.owner_id == subject),
                )
            )
            if food is None:
                raise UnknownFood(food_id)
            snapshot = {f: getattr(food, f) for f in MACRO_FIELDS}

        rows.append(MealLogItem(food_id=food_id, grams=grams, **snapshot))
    return rows


def _portion(value: Decimal | None, grams: Decimal) -> float | None:
    """A per-100g snapshot value scaled to the logged portion."""
    if value is None:
        return None
    return float(Decimal(value) * grams / 100)


async def day_totals(session: AsyncSession, *, subject: str, local_date: str, tz: str) -> dict:
    """Sum of everything eaten on one calendar day in the profile timezone.

    Planned entries are excluded — a plan is not intake until confirmed.
    """
    start, end = _day_window(local_date, tz)
    result = await session.execute(
        select(MealLogItem.grams, *(getattr(MealLogItem, f) for f in MACRO_FIELDS))
        .join(MealLog)
        .where(
            MealLog.subject == subject,
            MealLog.planned.is_(False),
            MealLog.ts >= start,
            MealLog.ts < end,
        )
    )
    totals = dict.fromkeys(MACRO_FIELDS, Decimal(0))
    count = 0
    for grams, *macros in result:
        count += 1
        for name, value in zip(MACRO_FIELDS, macros, strict=True):
            if value is not None:
                totals[name] += Decimal(value) * Decimal(grams) / 100
    return {
        "local_date": local_date,
        "items_logged": count,
        **{name: float(value) for name, value in totals.items()},
    }


def log_payload(log: MealLog, totals: dict, tz: str) -> dict:
    """JSON-safe shape shared by both adapters, so they cannot disagree."""
    return {
        "log_id": log.id,
        "ts": log.ts.isoformat(),
        "meal": log.meal,
        "input_mode": log.input_mode,
        "planned": log.planned,
        "notes": log.notes,
        "items": [
            {
                "food_id": item.food_id,
                "grams": float(item.grams),
                "kcal": _portion(item.kcal, item.grams),
                "protein_g": _portion(item.protein_g, item.grams),
                "carbs_g": _portion(item.carbs_g, item.grams),
                "fat_g": _portion(item.fat_g, item.grams),
                "fiber_g": _portion(item.fiber_g, item.grams),
            }
            for item in log.items
        ],
        "day_totals": totals,
        "server_time": servertime.echo(tz),
    }


async def log_meal(
    session: AsyncSession,
    *,
    subject: str,
    items: list[dict],
    meal: str | None = None,
    ts: str | datetime | None = None,
    input_mode: str = "text",
    notes: str | None = None,
) -> dict:
    """Create one eating event and return it with the day's running totals.

    The totals ride along so the client can react ("that puts you at 1 640
    kcal") without a second call. input_mode "plan" creates a planner entry:
    planned until revise_log confirms it eaten.
    """
    if meal is not None and meal not in MEALS:
        raise InvalidLog(f"meal must be one of {', '.join(MEALS)}")
    if input_mode not in INPUT_MODES:
        raise InvalidLog(f"input_mode must be one of {', '.join(INPUT_MODES)}")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone

    log = MealLog(
        subject=subject,
        ts=_parse_ts(ts, tz) or servertime.now(),
        meal=meal,
        input_mode=input_mode,
        planned=input_mode == "plan",
        notes=notes,
        items=await _snapshot_items(session, subject=subject, items=items),
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)

    totals = await day_totals(
        session, subject=subject, local_date=servertime.local_date(tz, log.ts), tz=tz
    )
    return log_payload(log, totals, tz)


async def revise_log(session: AsyncSession, *, subject: str, log_id: int, changes: dict) -> dict:
    """The one-sentence correction path: "that was 250 g, not 400".

    `changes` may carry ts, meal, planned, notes, and/or items. Items replace
    the whole list and re-snapshot from today's definitions — a correction
    states what was actually eaten. `planned: false` confirms a planner entry.
    Unknown fields fail loudly; silently dropping one would let a client
    believe it corrected something it didn't.
    """
    unknown = set(changes) - REVISABLE
    if unknown:
        raise InvalidLog(f"not revisable: {', '.join(sorted(unknown))}")
    if not changes:
        raise InvalidLog("nothing to change")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone

    log = await session.scalar(
        select(MealLog).where(MealLog.id == log_id, MealLog.subject == subject)
    )
    if log is None:
        raise LogNotFound(log_id)

    if "meal" in changes:
        if changes["meal"] is not None and changes["meal"] not in MEALS:
            raise InvalidLog(f"meal must be one of {', '.join(MEALS)}")
        log.meal = changes["meal"]
    if "ts" in changes:
        parsed = _parse_ts(changes["ts"], tz)
        if parsed is None:
            raise InvalidLog("ts cannot be cleared")
        log.ts = parsed
    if "planned" in changes:
        log.planned = bool(changes["planned"])
    if "notes" in changes:
        log.notes = changes["notes"]
    if "items" in changes:
        existing = {item.food_id: {f: getattr(item, f) for f in MACRO_FIELDS} for item in log.items}
        log.items = await _snapshot_items(
            session, subject=subject, items=changes["items"], keep=existing
        )

    await session.commit()
    await session.refresh(log)

    totals = await day_totals(
        session, subject=subject, local_date=servertime.local_date(tz, log.ts), tz=tz
    )
    return log_payload(log, totals, tz)
