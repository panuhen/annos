"""Exercise logging: sessions, sets, and the MET arithmetic.

Cardio calories are MET × bodyweight × hours, snapshotting the latest logged
bodyweight at log time — the same discipline as macro snapshots, so a
duration revision rescales from what was true then. The estimate is NULL
whenever a factor is honestly unknown (no weight ever logged, no duration,
no MET basis): an honest nothing beats a fabricated number.

Strength is tracked for load progression, not calories — a flat MET over the
session duration is all the precision the number deserves. Strength movements
live in a user-grown, user-scoped catalog: the server creates one on first
mention and matches case-insensitively within the owner's rows only.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.models import (
    EXERCISE_KINDS,
    EXERCISE_SOURCES,
    Activity,
    BodyMetric,
    Exercise,
    ExerciseLog,
    StrengthSet,
)

# What revise_exercise accepts. Sets replace the whole list, like meal items.
REVISABLE = frozenset({"ts", "kind", "activity_id", "duration_min", "planned", "notes", "sets"})

# The flat MET a strength (or other) session gets when it has a duration but
# no catalog activity. It's noise either way; don't pretend precision.
FLAT_MET = Decimal("5.0")


class UnknownActivity(Exception):
    """No such activity in the MET catalog."""

    def __init__(self, activity_id: int) -> None:
        super().__init__(f"no such activity: {activity_id}")
        self.activity_id = activity_id


class ExerciseLogNotFound(Exception):
    """No such session for this subject — same deliberate ambiguity as meals."""


class InvalidExercise(Exception):
    """The request shape is wrong: bad kind, sets on a run, no reps…"""


async def find_activity(
    session: AsyncSession, *, subject: str, query: str, limit: int = 10
) -> list[dict]:
    """Search the MET catalog, the same way find_food searches foods.

    Substring OR word-trigram so a short query qualifies against long
    Compendium descriptions, ranked by word_similarity so the plain activity
    outranks the compounds it starts. The typo arm diverges from find_food on
    purpose: every Compendium name is a long compound, so whole-string `%`
    similarity never clears its threshold — word_similarity > 0.4 does
    ("bicylcing" scores 0.43 against "Bicycling, general"; garbage scores 0).
    The catalog is global and English-only (a recorded decision) — the caller
    translates before searching.
    """
    query = query.strip()
    if not query:
        return []

    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    score = func.word_similarity(query, Activity.name).label("score")
    stmt = (
        select(Activity)
        .where(Activity.name.ilike(f"%{escaped}%", escape="\\") | (score > 0.4))
        .order_by(score.desc(), Activity.name.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [
        {
            "id": activity.id,
            "name": activity.name,
            "category": activity.category,
            "met": float(activity.met),
        }
        for activity in result.scalars()
    ]


async def _latest_weight(session: AsyncSession, *, subject: str) -> Decimal | None:
    """The most recent logged bodyweight, or None if none was ever logged."""
    return await session.scalar(
        select(BodyMetric.weight_kg)
        .where(BodyMetric.subject == subject, BodyMetric.weight_kg.is_not(None))
        .order_by(BodyMetric.date.desc())
        .limit(1)
    )


def _estimate(
    met: Decimal | None, weight_kg: Decimal | None, duration_min: Decimal | None
) -> Decimal | None:
    """MET × kg × h, or None when any factor is honestly unknown."""
    if met is None or weight_kg is None or duration_min is None:
        return None
    return Decimal(met) * Decimal(weight_kg) * Decimal(duration_min) / 60


async def _resolve_activity(session: AsyncSession, activity_id: int) -> Activity:
    activity = await session.scalar(select(Activity).where(Activity.id == activity_id))
    if activity is None:
        raise UnknownActivity(activity_id)
    return activity


async def _match_or_create_exercise(session: AsyncSession, *, subject: str, name: str) -> Exercise:
    """The caller's own movement vocabulary: match case-insensitively within
    their rows, create on first mention. Never another user's."""
    name = name.strip()
    if not name:
        raise InvalidExercise("an exercise needs a name")
    exercise = await session.scalar(
        select(Exercise).where(
            Exercise.owner_id == subject, func.lower(Exercise.name) == name.lower()
        )
    )
    if exercise is None:
        exercise = Exercise(owner_id=subject, name=name)
        session.add(exercise)
        await session.flush()
    return exercise


async def _build_sets(
    session: AsyncSession, *, subject: str, sets: list[dict]
) -> list[StrengthSet]:
    if not sets:
        raise InvalidExercise("a strength session needs at least one set, or none at all")
    rows = []
    for index, item in enumerate(sets, start=1):
        if not isinstance(item, dict):
            raise InvalidExercise("each set is {exercise, reps, weight_kg, rpe?}")
        unknown = set(item) - {"exercise", "reps", "weight_kg", "rpe"}
        if unknown:
            raise InvalidExercise(f"unknown set fields: {', '.join(sorted(unknown))}")
        try:
            exercise_name = str(item["exercise"])
            reps = int(item["reps"])
            weight = Decimal(str(item["weight_kg"]))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise InvalidExercise("each set needs exercise, reps and weight_kg") from exc
        if reps <= 0:
            raise InvalidExercise("reps must be positive")
        if weight < 0:
            raise InvalidExercise("weight_kg cannot be negative (0 is a bodyweight set)")
        rpe = item.get("rpe")
        if rpe is not None:
            rpe = Decimal(str(rpe))
            if not 1 <= rpe <= 10:
                raise InvalidExercise("rpe is the 1-10 scale")
        exercise = await _match_or_create_exercise(session, subject=subject, name=exercise_name)
        rows.append(
            StrengthSet(exercise_id=exercise.id, set_no=index, reps=reps, weight_kg=weight, rpe=rpe)
        )
    return rows


def _validate_shape(kind: str, activity_id: int | None, sets: list[dict] | None) -> None:
    """The combinations that make no sense fail loudly, never silently."""
    if kind not in EXERCISE_KINDS:
        raise InvalidExercise(f"kind must be one of {', '.join(EXERCISE_KINDS)}")
    if sets and kind != "strength":
        raise InvalidExercise("sets belong to a strength session")
    if activity_id is not None and kind == "strength":
        raise InvalidExercise(
            "a strength session takes sets, not a catalog activity — "
            "use kind cardio/other for activity-based logging"
        )


def _parse_duration(value) -> Decimal | None:
    if value is None:
        return None
    try:
        duration = Decimal(str(value))
    except ArithmeticError as exc:
        raise InvalidExercise(f"not a duration: {value!r}") from exc
    if duration <= 0:
        raise InvalidExercise("duration_min must be positive")
    return duration


def session_payload(log: ExerciseLog) -> dict:
    """The session itself, shared by the log/revise responses and the daily
    summary — one shape, so a client that revises a session it didn't create
    reads the same fields it would have been answered with."""
    return {
        "log_id": log.id,
        "ts": log.ts.isoformat(),
        "kind": log.kind,
        "activity": (
            {
                "id": log.activity.id,
                "name": log.activity.name,
                "category": log.activity.category,
                "met": float(log.activity.met),
            }
            if log.activity is not None
            else None
        ),
        "duration_min": float(log.duration_min) if log.duration_min is not None else None,
        "kcal_estimate": float(log.kcal_estimate) if log.kcal_estimate is not None else None,
        "planned": log.planned,
        "source": log.source,
        "notes": log.notes,
        "sets": [
            {
                "set_no": s.set_no,
                "exercise": s.exercise.name if s.exercise is not None else None,
                "reps": s.reps,
                "weight_kg": float(s.weight_kg),
                "rpe": float(s.rpe) if s.rpe is not None else None,
            }
            for s in log.sets
        ],
    }


def log_payload(log: ExerciseLog, tz: str, *, day_type: str, day_type_source: str) -> dict:
    """JSON-safe shape shared by both adapters, like meals.log_payload.

    Carries the day's resolved type so the client sees the consequence of the
    session ("that makes today a training day") without a second call.
    """
    return {
        **session_payload(log),
        "date": servertime.local_date(tz, log.ts),
        "day_type": day_type,
        "day_type_source": day_type_source,
        "server_time": servertime.echo(tz),
    }


async def _payload_with_day(
    session: AsyncSession, log: ExerciseLog, *, subject: str, tz: str
) -> dict:
    # Local import: days imports nothing from here, but keeping the dependency
    # one-way at module load avoids a cycle if that ever changes.
    from datetime import date as date_type

    from annos.domain import days as days_domain

    day = date_type.fromisoformat(servertime.local_date(tz, log.ts))
    day_type, source = await days_domain.resolve_day_type(session, subject=subject, on=day, tz=tz)
    return log_payload(log, tz, day_type=day_type, day_type_source=source)


async def log_exercise(
    session: AsyncSession,
    *,
    subject: str,
    kind: str,
    activity_id: int | None = None,
    duration_min: float | None = None,
    sets: list[dict] | None = None,
    ts: str | datetime | None = None,
    planned: bool = False,
    source: str = "user",
    notes: str | None = None,
) -> dict:
    """Record one session. Something must be said about it: an activity, a
    duration, sets, or at least a note — an empty session is a no-op, not data.
    """
    _validate_shape(kind, activity_id, sets)
    if source not in EXERCISE_SOURCES:
        raise InvalidExercise(f"source must be one of {', '.join(EXERCISE_SOURCES)}")
    duration = _parse_duration(duration_min)
    if activity_id is None and duration is None and not sets and notes is None:
        raise InvalidExercise("an empty session is not loggable — state something about it")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone

    activity = (
        await _resolve_activity(session, int(activity_id)) if activity_id is not None else None
    )
    met = Decimal(activity.met) if activity is not None else (FLAT_MET if duration else None)
    weight = await _latest_weight(session, subject=subject)

    log = ExerciseLog(
        subject=subject,
        ts=meals_domain._parse_ts(ts, tz) or servertime.now(),
        kind=kind,
        activity_id=activity.id if activity is not None else None,
        duration_min=duration,
        weight_kg=weight,
        kcal_estimate=_estimate(met, weight, duration),
        planned=bool(planned),
        source=source,
        notes=notes,
        sets=await _build_sets(session, subject=subject, sets=sets) if sets else [],
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return await _payload_with_day(session, log, subject=subject, tz=tz)


async def revise_exercise(
    session: AsyncSession, *, subject: str, log_id: int, changes: dict
) -> dict:
    """The correction path: "that was 45 minutes, not 30".

    Recomputes the estimate from the *stored* bodyweight snapshot — what was
    true at log time — with the revised activity/duration. Sets replace the
    whole list. {"planned": false} confirms a planned session, which is the
    moment it starts deriving the day's type.
    """
    unknown = set(changes) - REVISABLE
    if unknown:
        raise InvalidExercise(f"not revisable: {', '.join(sorted(unknown))}")
    if not changes:
        raise InvalidExercise("nothing to change")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone

    log = await session.scalar(
        select(ExerciseLog).where(ExerciseLog.id == log_id, ExerciseLog.subject == subject)
    )
    if log is None:
        raise ExerciseLogNotFound(log_id)

    kind = changes.get("kind", log.kind)
    activity_id = changes.get("activity_id", log.activity_id)
    sets = changes.get("sets")
    final_sets_exist = bool(sets) if "sets" in changes else bool(log.sets)
    _validate_shape(kind, activity_id, sets if sets else None)
    if final_sets_exist and kind != "strength":
        raise InvalidExercise("sets belong to a strength session")

    if "ts" in changes:
        parsed = meals_domain._parse_ts(changes["ts"], tz)
        if parsed is None:
            raise InvalidExercise("ts cannot be cleared")
        log.ts = parsed
    log.kind = kind
    if "activity_id" in changes:
        log.activity_id = (
            (await _resolve_activity(session, int(changes["activity_id"]))).id
            if changes["activity_id"] is not None
            else None
        )
    if "duration_min" in changes:
        log.duration_min = _parse_duration(changes["duration_min"])
    if "planned" in changes:
        log.planned = bool(changes["planned"])
    if "notes" in changes:
        log.notes = changes["notes"]
    if "sets" in changes:
        log.sets = await _build_sets(session, subject=subject, sets=sets) if sets else []

    # Re-derive the estimate from the log-time weight snapshot.
    activity = (
        await _resolve_activity(session, log.activity_id) if log.activity_id is not None else None
    )
    met = (
        Decimal(activity.met) if activity is not None else (FLAT_MET if log.duration_min else None)
    )
    log.kcal_estimate = _estimate(
        met,
        Decimal(log.weight_kg) if log.weight_kg is not None else None,
        Decimal(log.duration_min) if log.duration_min is not None else None,
    )

    await session.commit()
    await session.refresh(log)
    return await _payload_with_day(session, log, subject=subject, tz=tz)


async def delete_exercise(session: AsyncSession, *, subject: str, log_id: int) -> dict:
    """Erase a session that never happened — a duplicate, a test entry.

    Returns the day's resolved type after the removal, because deleting the
    only session of a derived training day turns it back into a rest day.
    """
    from datetime import date as date_type

    from annos.domain import days as days_domain

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone

    log = await session.scalar(
        select(ExerciseLog).where(ExerciseLog.id == log_id, ExerciseLog.subject == subject)
    )
    if log is None:
        raise ExerciseLogNotFound(log_id)

    local_date = servertime.local_date(tz, log.ts)
    await session.delete(log)
    await session.commit()

    day_type, source = await days_domain.resolve_day_type(
        session, subject=subject, on=date_type.fromisoformat(local_date), tz=tz
    )
    return {
        "deleted_log_id": log_id,
        "date": local_date,
        "day_type": day_type,
        "day_type_source": source,
        "server_time": servertime.echo(tz),
    }
