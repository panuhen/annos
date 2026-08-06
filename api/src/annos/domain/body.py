"""Bodyweight and goal phases.

`log_weight` upserts on (subject, date): the scale said one thing today, and
saying it again replaces rather than duplicates. The smoothed trend is never
stored — it is computed where it is read, and interpreting its noise is the
client's job, not this server's.

`set_goal_phase` appends: the previous phase is closed the day before the new
one starts, never rewritten, so history always evaluates a day against the
target that was in force then.
"""

from datetime import date as date_type
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import profile as profile_domain
from annos.models import GOAL_KINDS, BodyMetric, GoalPhase


class InvalidMetric(Exception):
    """The measurement is missing, out of range, or the date is malformed."""


class InvalidPhase(Exception):
    """The phase targets or dates don't make sense."""


def _parse_date(value: str | date_type | None, tz: str) -> date_type:
    """A stated calendar date, or today in the profile timezone."""
    if value is None:
        return date_type.fromisoformat(servertime.local_date(tz))
    if isinstance(value, date_type):
        return value
    try:
        return date_type.fromisoformat(value)
    except ValueError as exc:
        raise InvalidMetric(f"not an ISO 8601 date: {value!r}") from exc


def metric_payload(metric: BodyMetric, tz: str) -> dict:
    return {
        "date": metric.date.isoformat(),
        "weight_kg": float(metric.weight_kg) if metric.weight_kg is not None else None,
        "waist_cm": float(metric.waist_cm) if metric.waist_cm is not None else None,
        "notes": metric.notes,
        "server_time": servertime.echo(tz),
    }


async def log_weight(
    session: AsyncSession,
    *,
    subject: str,
    weight_kg: float | None = None,
    date: str | date_type | None = None,
    waist_cm: float | None = None,
    notes: str | None = None,
) -> dict:
    """Record today's (or a stated day's) measurements. Upserts on the day.

    A re-log replaces only the fields it carries: logging waist in the evening
    must not erase the weight logged in the morning.
    """
    if weight_kg is None and waist_cm is None and notes is None:
        raise InvalidMetric("nothing to log: weight_kg, waist_cm and notes all absent")
    if weight_kg is not None and not 0 < weight_kg < 500:
        raise InvalidMetric("weight_kg out of range")
    if waist_cm is not None and not 0 < waist_cm < 500:
        raise InvalidMetric("waist_cm out of range")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone
    day = _parse_date(date, tz)

    carried = {
        name: value
        for name, value in (("weight_kg", weight_kg), ("waist_cm", waist_cm), ("notes", notes))
        if value is not None
    }
    stmt = (
        pg_insert(BodyMetric)
        .values(subject=subject, date=day, **carried)
        .on_conflict_do_update(
            index_elements=["subject", "date"],
            # onupdate= is ORM-level and this is a core upsert, so updated_at
            # is refreshed by hand.
            set_={**carried, "updated_at": servertime.now()},
        )
        .returning(BodyMetric)
    )
    metric = (await session.execute(stmt)).scalar_one()
    await session.commit()
    return metric_payload(metric, tz)


def _phase_fields(phase: GoalPhase) -> dict:
    return {
        "phase_id": phase.id,
        "kind": phase.kind,
        "start_date": phase.start_date.isoformat(),
        "end_date": phase.end_date.isoformat() if phase.end_date is not None else None,
        "kcal_target_training": phase.kcal_target_training,
        "kcal_target_rest": phase.kcal_target_rest,
        "protein_target_g": phase.protein_target_g,
        "rate_target_kg_per_week": (
            float(phase.rate_target_kg_per_week)
            if phase.rate_target_kg_per_week is not None
            else None
        ),
    }


def phase_payload(phase: GoalPhase, tz: str) -> dict:
    return {**_phase_fields(phase), "server_time": servertime.echo(tz)}


async def active_phase(session: AsyncSession, *, subject: str, on: date_type) -> GoalPhase | None:
    """The phase in force on a given day — how history is always evaluated."""
    return await session.scalar(
        select(GoalPhase)
        .where(
            GoalPhase.subject == subject,
            GoalPhase.start_date <= on,
            (GoalPhase.end_date.is_(None)) | (GoalPhase.end_date >= on),
        )
        .order_by(GoalPhase.start_date.desc())
        .limit(1)
    )


async def list_goal_phases(session: AsyncSession, *, subject: str) -> dict:
    """Every phase ever set, newest first — the progression, not just today's target.

    Phases append and close (see `set_goal_phase`), so this list *is* the goal
    history: the open phase has `end_date` null, everything below it reads as
    what the targets were and when they changed.
    """
    profile = await profile_domain.get_profile(session, subject=subject)
    phases = await session.scalars(
        select(GoalPhase).where(GoalPhase.subject == subject).order_by(GoalPhase.start_date.desc())
    )
    return {
        "phases": [_phase_fields(phase) for phase in phases],
        "server_time": servertime.echo(profile.timezone),
    }


async def set_goal_phase(
    session: AsyncSession,
    *,
    subject: str,
    kind: str,
    kcal_training: int,
    kcal_rest: int,
    protein_g: int,
    rate_target: float | None = None,
    start_date: str | date_type | None = None,
) -> dict:
    """Open a new phase, closing the current one the day before it starts."""
    if kind not in GOAL_KINDS:
        raise InvalidPhase(f"kind must be one of {', '.join(GOAL_KINDS)}")
    if min(kcal_training, kcal_rest, protein_g) <= 0:
        raise InvalidPhase("targets must be positive")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone
    try:
        start = _parse_date(start_date, tz)
    except InvalidMetric as exc:
        raise InvalidPhase(str(exc)) from exc

    current = await session.scalar(
        select(GoalPhase).where(GoalPhase.subject == subject, GoalPhase.end_date.is_(None))
    )
    if current is not None:
        if current.start_date >= start:
            # Same-day (or earlier) restart cannot close the old phase on the
            # day before without violating end >= start. Overlapping rewrites
            # of history are refused rather than resolved cleverly.
            raise InvalidPhase(
                f"a phase already runs from {current.start_date.isoformat()}; "
                "a new one must start after that"
            )
        current.end_date = start - timedelta(days=1)

    phase = GoalPhase(
        subject=subject,
        kind=kind,
        start_date=start,
        kcal_target_training=kcal_training,
        kcal_target_rest=kcal_rest,
        protein_target_g=protein_g,
        rate_target_kg_per_week=rate_target,
    )
    session.add(phase)
    await session.commit()
    await session.refresh(phase)

    payload = phase_payload(phase, tz)
    payload["closed_previous"] = (
        {"phase_id": current.id, "end_date": current.end_date.isoformat()}
        if current is not None
        else None
    )
    return payload
