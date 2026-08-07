"""What kind of day a date is — the half of the target the phase can't know.

A day's target is the phase in force on that date plus the day's type. The
type resolves in order: a manual mark wins (the user saying what the day is
beats any derivation, in both directions), then exercise-derived once
exercise logging exists, then rest. The resolution's source travels with the
answer so a client never has to guess whether "rest" was said or assumed.
"""

from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import profile as profile_domain
from annos.models import DAY_TYPES, DayTypeMark


class InvalidDayType(Exception):
    """Not a day type, or the date is malformed."""


def _parse_date(value: str | date_type | None, tz: str) -> date_type:
    if value is None:
        return date_type.fromisoformat(servertime.local_date(tz))
    if isinstance(value, date_type):
        return value
    try:
        return date_type.fromisoformat(value)
    except ValueError as exc:
        raise InvalidDayType(f"not an ISO 8601 date: {value!r}") from exc


async def set_day_type(
    session: AsyncSession,
    *,
    subject: str,
    day_type: str,
    date: str | date_type | None = None,
) -> dict:
    """Mark a day training or rest. Upserts on the day: saying it again
    replaces, and marking the other way overrides what a derivation would say.
    """
    if day_type not in DAY_TYPES:
        raise InvalidDayType(f"day_type must be one of {', '.join(DAY_TYPES)}")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone
    day = _parse_date(date, tz)

    stmt = (
        pg_insert(DayTypeMark)
        .values(subject=subject, date=day, day_type=day_type)
        .on_conflict_do_update(
            index_elements=["subject", "date"],
            # onupdate= is ORM-level and this is a core upsert, so updated_at
            # is refreshed by hand.
            set_={"day_type": day_type, "updated_at": servertime.now()},
        )
        .returning(DayTypeMark)
    )
    mark = (await session.execute(stmt)).scalar_one()
    await session.commit()
    return {
        "date": mark.date.isoformat(),
        "day_type": mark.day_type,
        "server_time": servertime.echo(tz),
    }


async def resolve_day_type(
    session: AsyncSession, *, subject: str, on: date_type, tz: str
) -> tuple[str, str]:
    """The day's type and where it came from: ("training"|"rest",
    "manual"|"derived"|"default").

    A manual mark wins in both directions. Unmarked, a day with any
    non-planned exercise session resolves as derived training — the session
    is a fact, not an assumption, so the source says "derived". A planned
    session derives nothing: a plan is not training until confirmed. Only
    then does the day fall to rest by default, labelled as the assumption
    it is. The day boundary is the profile timezone's, same as everywhere.
    """
    from annos.domain import meals as meals_domain
    from annos.models import ExerciseLog

    mark = await session.scalar(
        select(DayTypeMark).where(DayTypeMark.subject == subject, DayTypeMark.date == on)
    )
    if mark is not None:
        return mark.day_type, "manual"

    start, end = meals_domain._day_window(on.isoformat(), tz)
    trained = await session.scalar(
        select(ExerciseLog.id)
        .where(
            ExerciseLog.subject == subject,
            ExerciseLog.planned.is_(False),
            ExerciseLog.ts >= start,
            ExerciseLog.ts < end,
        )
        .limit(1)
    )
    if trained is not None:
        return "training", "derived"
    return "rest", "default"
