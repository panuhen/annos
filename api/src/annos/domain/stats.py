"""The stats read views: what the logging was for.

Three questions, in value order. Is the plan working — the smoothed weight
trend against the phase's rate target. What is the user actually burning —
the measured TDEE (intake vs the weight trend over a rolling window), the
number no formula can give. Did the user do what they said — the weekly
ledger of intake against the targets that were in force, judged day by day
against the phase and day type that held *then*.

Everything here is arithmetic over data the loggers already collect; there
are no stats tables. Two disciplines carry through from the rest of the
domain. Honesty: a TDEE that cannot be measured is null with the reason,
never a formula guess, and every average says which days it covers.
And exercise kcal never enters the energy arithmetic — the measured TDEE
already contains all activity, so subtracting estimate-grade burn would
double-count it. Weekly exercise kcal rides along as a fact, nothing more.
"""

import math
from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import body as body_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.models import (
    BodyMetric,
    DayTypeMark,
    Exercise,
    ExerciseLog,
    GoalPhase,
    MealLog,
    MealLogItem,
)

MAX_WEIGHT_DAYS = 365
MAX_WEEKS = 26

# The adaptive-TDEE parameters, pinned 2026-08-07 (re:call "Adaptive TDEE
# method"); tunable by daily use. The window ends *yesterday* — today's
# half-logged intake would drag the average down.
TDEE_WINDOW_DAYS = 21
TDEE_MIN_LOGGED = math.ceil(TDEE_WINDOW_DAYS * 0.8)  # refuse below this
TDEE_MARGINAL_LOGGED = math.ceil(TDEE_WINDOW_DAYS * 0.9)  # low confidence below this
TDEE_SPARSE_WEIGH_INS = 8  # low confidence below this many weigh-in days
KCAL_PER_KG = 7700

SMOOTHING_DAYS = 7  # trailing window for the smoothed weight trend
RATE_SPAN_DAYS = 14  # weight_history's trailing rate is measured over this


class InvalidQuery(Exception):
    """The window is out of range or not a number."""


class UnknownExercise(Exception):
    """No movement with this name in the caller's catalog."""

    def __init__(self, name: str) -> None:
        super().__init__(f"no exercise named {name!r} in your catalog")
        self.name = name


def _parse_window(value, *, maximum: int, name: str) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidQuery(f"{name} must be a number, not {value!r}") from exc
    if not 1 <= value <= maximum:
        raise InvalidQuery(f"{name} must be between 1 and {maximum}")
    return value


async def _weights_by_date(
    session: AsyncSession, *, subject: str, first: date_type, last: date_type
) -> dict[date_type, Decimal]:
    """Logged bodyweights per calendar day, for smoothing. One row per day
    by the upsert's design."""
    rows = await session.execute(
        select(BodyMetric.date, BodyMetric.weight_kg).where(
            BodyMetric.subject == subject,
            BodyMetric.weight_kg.is_not(None),
            BodyMetric.date >= first,
            BodyMetric.date <= last,
        )
    )
    return {row.date: Decimal(row.weight_kg) for row in rows}


def _smoothed_at(weights: dict[date_type, Decimal], anchor: date_type) -> float | None:
    """The trailing 7-day mean at a date, over the weigh-ins that exist.

    Gaps shrink the divisor rather than fabricating values; a week with no
    weigh-in at all has no smoothed value, honestly.
    """
    values = [
        weights[anchor - timedelta(days=back)]
        for back in range(SMOOTHING_DAYS)
        if anchor - timedelta(days=back) in weights
    ]
    if not values:
        return None
    return float(sum(values) / len(values))


async def _intake_by_date(
    session: AsyncSession, *, subject: str, first: date_type, last: date_type, tz: str
) -> dict[date_type, dict[str, float]]:
    """Non-planned intake per local calendar day: kcal and protein.

    A date present in the result is a *logged day* — at least one non-planned
    meal log fell on it. Planned entries are not intake and never appear.
    """
    start, _ = meals_domain._day_window(first.isoformat(), tz)
    _, end = meals_domain._day_window(last.isoformat(), tz)
    rows = await session.execute(
        select(MealLog.ts, MealLogItem.grams, MealLogItem.kcal, MealLogItem.protein_g)
        .join(MealLogItem, MealLogItem.log_id == MealLog.id)
        .where(
            MealLog.subject == subject,
            MealLog.planned.is_(False),
            MealLog.ts >= start,
            MealLog.ts < end,
        )
    )
    days: dict[date_type, dict[str, float]] = {}
    for ts, grams, kcal, protein in rows:
        day = date_type.fromisoformat(servertime.local_date(tz, ts))
        bucket = days.setdefault(day, {"kcal": 0.0, "protein_g": 0.0})
        bucket["kcal"] += float(Decimal(kcal) * Decimal(grams) / 100)
        bucket["protein_g"] += float(Decimal(protein) * Decimal(grams) / 100)
    return days


async def weight_history(session: AsyncSession, *, subject: str, days: int = 30) -> dict:
    """The weight series, oldest first: raw points, the smoothed trend, and
    the trailing rate.

    The window is the last `days` calendar days in the profile timezone,
    today included, like recent_meals. Points are the body_metrics rows as
    logged — weight, waist, notes — because this is also the read path for
    correcting them: log_weight upserts on the date it is told. The smoothed
    series exists only on dates that have a weigh-in; the rate is measured
    over the trailing 14 days of smoothed values and is null when either
    anchor has no weigh-in within its smoothing week.
    """
    days = _parse_window(days, maximum=MAX_WEIGHT_DAYS, name="days")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone

    today = date_type.fromisoformat(servertime.local_date(tz))
    first = today - timedelta(days=days - 1)

    rows = (
        (
            await session.execute(
                select(BodyMetric)
                .where(
                    BodyMetric.subject == subject,
                    BodyMetric.date >= first,
                    BodyMetric.date <= today,
                )
                .order_by(BodyMetric.date)
            )
        )
        .scalars()
        .all()
    )
    # Smoothing looks back past the window's first day, so fetch the extra week.
    weights = await _weights_by_date(
        session, subject=subject, first=first - timedelta(days=SMOOTHING_DAYS - 1), last=today
    )

    smoothed = [
        {"date": row.date.isoformat(), "weight_kg": round(_smoothed_at(weights, row.date), 2)}
        for row in rows
        if row.weight_kg is not None
    ]

    rate = None
    weigh_dates = sorted(d for d in weights if first <= d <= today)
    if weigh_dates:
        anchor_end = weigh_dates[-1]
        anchor_start = anchor_end - timedelta(days=RATE_SPAN_DAYS)
        s_end = _smoothed_at(weights, anchor_end)
        s_start = _smoothed_at(weights, anchor_start)
        if s_end is not None and s_start is not None:
            rate = round((s_end - s_start) / RATE_SPAN_DAYS * 7, 2)

    return {
        "days": days,
        "points": [
            {
                "date": row.date.isoformat(),
                "weight_kg": float(row.weight_kg) if row.weight_kg is not None else None,
                "waist_cm": float(row.waist_cm) if row.waist_cm is not None else None,
                "notes": row.notes,
            }
            for row in rows
        ],
        "smoothed": smoothed,
        "rate_kg_per_week": rate,
        "server_time": servertime.echo(tz),
    }


async def _tdee_block(session: AsyncSession, *, subject: str, profile, today: date_type) -> dict:
    """The measured-TDEE block, shared verbatim by get_tdee and weekly_review
    so the two cannot drift. No server_time — the caller's payload carries it.

    TDEE ≈ avg daily intake − (weight change × 7700) / days, over the last 21
    complete days. Refusals return null with machine-readable reasons; a
    computable estimate still flags its weaknesses as low confidence. The
    inputs ride along so the arithmetic is auditable, per the not-a-black-box
    rule; the interpretation is the client's.
    """
    tz = profile.timezone
    end = today - timedelta(days=1)
    start = end - timedelta(days=TDEE_WINDOW_DAYS - 1)

    intake = await _intake_by_date(session, subject=subject, first=start, last=end, tz=tz)
    weights = await _weights_by_date(
        session, subject=subject, first=start - timedelta(days=SMOOTHING_DAYS - 1), last=end
    )

    logged_days = len(intake)
    weigh_in_days = sum(1 for d in weights if start <= d <= end)
    s_start = _smoothed_at(weights, start)
    s_end = _smoothed_at(weights, end)
    intake_avg = sum(day["kcal"] for day in intake.values()) / logged_days if logged_days else None

    reasons = []
    account_since = date_type.fromisoformat(servertime.local_date(tz, profile.created_at))
    if account_since > start:
        reasons.append("insufficient_history")
    if logged_days < TDEE_MIN_LOGGED:
        reasons.append("insufficient_logging")
    if s_start is None or s_end is None:
        reasons.append("insufficient_weight_data")

    tdee_kcal = None
    confidence = None
    weight_change = None
    if not reasons:
        weight_change = s_end - s_start
        tdee_kcal = round(intake_avg - (weight_change * KCAL_PER_KG) / TDEE_WINDOW_DAYS)
        phase = await body_domain.active_phase(session, subject=subject, on=today)
        # The first weeks of a new phase are dominated by water and glycogen
        # shifts; the estimate is shown, flagged, never hidden.
        if phase is not None and phase.start_date > start:
            reasons.append("new_phase_water_shift")
        if logged_days < TDEE_MARGINAL_LOGGED:
            reasons.append("marginal_logging")
        if weigh_in_days < TDEE_SPARSE_WEIGH_INS:
            reasons.append("sparse_weigh_ins")
        confidence = "low" if reasons else "ok"

    return {
        "tdee_kcal": tdee_kcal,
        "confidence": confidence,
        "reasons": reasons,
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": TDEE_WINDOW_DAYS,
        },
        "coverage": {
            "logged_days": logged_days,
            "required_days": TDEE_MIN_LOGGED,
            "weigh_in_days": weigh_in_days,
        },
        "inputs": {
            "intake_avg_kcal": round(intake_avg, 1) if intake_avg is not None else None,
            "weight_trend_start_kg": round(s_start, 2) if s_start is not None else None,
            "weight_trend_end_kg": round(s_end, 2) if s_end is not None else None,
            "weight_change_kg": round(weight_change, 2) if weight_change is not None else None,
        },
    }


async def get_tdee(session: AsyncSession, *, subject: str) -> dict:
    """The measured TDEE: estimate, confidence, coverage, and the inputs."""
    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone
    today = date_type.fromisoformat(servertime.local_date(tz))
    block = await _tdee_block(session, subject=subject, profile=profile, today=today)
    return {**block, "server_time": servertime.echo(tz)}


def _week_starts(today: date_type, weeks: int) -> list[date_type]:
    """The Mondays of the last `weeks` ISO weeks, current week first."""
    current = today - timedelta(days=today.weekday())
    return [current - timedelta(weeks=back) for back in range(weeks)]


def _resolve_phase(phases: list[GoalPhase], on: date_type) -> GoalPhase | None:
    for phase in phases:
        if phase.start_date <= on and (phase.end_date is None or phase.end_date >= on):
            return phase
    return None


async def weekly_review(session: AsyncSession, *, subject: str, weeks: int = 4) -> dict:
    """The weekly ledger, newest first, plus the TDEE block: the one-call
    answer to "how is it going?".

    Weeks are ISO weeks (Monday–Sunday) in the profile timezone; the current
    week rides along flagged `partial`. Intake averages cover *logged days*
    only — a skipped day is missing data, not a zero-calorie day — and the
    target average covers the same days, judged against the phase and day
    type in force on each (`targeted_days` says how many of the logged days
    had a phase at all). Weight endpoints are the trailing-7-day smoothed
    values at the week's edges. Exercise kcal is a fact in the row, never
    part of the energy arithmetic.
    """
    weeks = _parse_window(weeks, maximum=MAX_WEEKS, name="weeks")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone
    today = date_type.fromisoformat(servertime.local_date(tz))

    starts = _week_starts(today, weeks)
    span_first = starts[-1]

    intake = await _intake_by_date(session, subject=subject, first=span_first, last=today, tz=tz)
    weights = await _weights_by_date(
        session,
        subject=subject,
        first=span_first - timedelta(days=SMOOTHING_DAYS - 1),
        last=today,
    )
    phases = (
        (
            await session.execute(
                select(GoalPhase)
                .where(GoalPhase.subject == subject)
                .order_by(GoalPhase.start_date.desc())
            )
        )
        .scalars()
        .all()
    )
    marks = {
        row.date: row.day_type
        for row in (
            await session.execute(
                select(DayTypeMark).where(
                    DayTypeMark.subject == subject,
                    DayTypeMark.date >= span_first,
                    DayTypeMark.date <= today,
                )
            )
        ).scalars()
    }
    span_start_utc, _ = meals_domain._day_window(span_first.isoformat(), tz)
    _, span_end_utc = meals_domain._day_window(today.isoformat(), tz)
    sessions = (
        (
            await session.execute(
                select(ExerciseLog).where(
                    ExerciseLog.subject == subject,
                    ExerciseLog.planned.is_(False),
                    ExerciseLog.ts >= span_start_utc,
                    ExerciseLog.ts < span_end_utc,
                )
            )
        )
        .scalars()
        .all()
    )
    sessions_by_date: dict[date_type, list[ExerciseLog]] = {}
    for log in sessions:
        day = date_type.fromisoformat(servertime.local_date(tz, log.ts))
        sessions_by_date.setdefault(day, []).append(log)

    def day_type_of(day: date_type) -> str:
        # The same manual → derived → rest order as domain.days, resolved
        # against the bulk-fetched rows instead of per-day queries.
        if day in marks:
            return marks[day]
        if day in sessions_by_date:
            return "training"
        return "rest"

    rows = []
    for week_start in starts:
        week_end = week_start + timedelta(days=6)
        last_day = min(week_end, today)

        week_days = [
            week_start + timedelta(days=offset)
            for offset in range((last_day - week_start).days + 1)
        ]
        logged = [day for day in week_days if day in intake]

        kcal_avg = (
            round(sum(intake[day]["kcal"] for day in logged) / len(logged), 1) if logged else None
        )
        protein_avg = (
            round(sum(intake[day]["protein_g"] for day in logged) / len(logged), 1)
            if logged
            else None
        )

        # Targets over the same logged days, each judged against the phase
        # and day type in force on it. Days before any phase have no target
        # and stay out of the average, counted honestly.
        kcal_targets = []
        protein_targets = []
        deltas = []
        for day in logged:
            phase = _resolve_phase(phases, day)
            if phase is None:
                continue
            training = day_type_of(day) == "training"
            kcal_target = phase.kcal_target_training if training else phase.kcal_target_rest
            protein_target = (
                phase.protein_target_training if training else phase.protein_target_rest
            )
            kcal_targets.append(kcal_target)
            protein_targets.append(protein_target)
            deltas.append(intake[day]["kcal"] - kcal_target)

        week_sessions = [log for day in week_days for log in sessions_by_date.get(day, [])]
        strength_sets = [s for log in week_sessions if log.kind == "strength" for s in log.sets]

        s_start = _smoothed_at(weights, week_start)
        s_end = _smoothed_at(weights, last_day)

        rows.append(
            {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "partial": week_end > today,
                "days_logged": len(logged),
                "days_in_week": len(week_days),
                "kcal_avg": kcal_avg,
                "kcal_target_avg": (
                    round(sum(kcal_targets) / len(kcal_targets), 1) if kcal_targets else None
                ),
                "kcal_delta_avg": round(sum(deltas) / len(deltas), 1) if deltas else None,
                "targeted_days": len(kcal_targets),
                "protein_avg_g": protein_avg,
                "protein_target_avg_g": (
                    round(sum(protein_targets) / len(protein_targets), 1)
                    if protein_targets
                    else None
                ),
                "weight_trend_start_kg": round(s_start, 2) if s_start is not None else None,
                "weight_trend_end_kg": round(s_end, 2) if s_end is not None else None,
                "weight_change_kg": (
                    round(s_end - s_start, 2) if s_start is not None and s_end is not None else None
                ),
                "sessions": len(week_sessions),
                "cardio_min": round(
                    sum(
                        float(log.duration_min)
                        for log in week_sessions
                        if log.kind == "cardio" and log.duration_min is not None
                    ),
                    1,
                ),
                "exercise_kcal": round(
                    sum(
                        float(log.kcal_estimate)
                        for log in week_sessions
                        if log.kcal_estimate is not None
                    ),
                    1,
                ),
                "strength_volume_kg": round(
                    sum(s.reps * float(s.weight_kg) for s in strength_sets), 1
                ),
                "strength_sets": len(strength_sets),
            }
        )

    active = await body_domain.active_phase(session, subject=subject, on=today)
    return {
        "weeks": rows,
        "tdee": await _tdee_block(session, subject=subject, profile=profile, today=today),
        "active_phase": body_domain._phase_fields(active) if active is not None else None,
        "profile_context": {
            "dietary_prefs": profile.dietary_prefs,
            "coaching_notes": profile.coaching_notes,
        },
        "server_time": servertime.echo(tz),
    }


def _e1rm(reps: int, weight_kg: float) -> float:
    """Epley: the estimated single-rep max behind a set."""
    return weight_kg * (1 + reps / 30)


def _e5rm(e1rm: float) -> float:
    """The estimated 5-rep max, the trend unit — inverse Epley at 5 reps."""
    return e1rm / (1 + 5 / 30)


async def training_history(
    session: AsyncSession, *, subject: str, exercise: str | None = None, weeks: int = 8
) -> dict:
    """Training over the last ISO weeks, newest first; optionally one
    movement's progression.

    The weekly rows aggregate non-planned sessions: count, cardio minutes,
    the exercise-kcal fact, set count, and strength volume (reps × kg over
    every set — a bodyweight set adds zero). With `exercise` (a name from
    the caller's own catalog, matched case-insensitively) the answer also
    carries that movement's per-session top set and its e5RM (Epley), the
    load-progression trend. Bodyweight sets carry no load to estimate and
    stay out of the e5RM; a session where the movement only appeared
    bodyweight reports a null e5rm rather than a fabricated number.
    """
    weeks = _parse_window(weeks, maximum=MAX_WEEKS, name="weeks")

    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone
    today = date_type.fromisoformat(servertime.local_date(tz))

    starts = _week_starts(today, weeks)
    span_first = starts[-1]
    span_start_utc, _ = meals_domain._day_window(span_first.isoformat(), tz)
    _, span_end_utc = meals_domain._day_window(today.isoformat(), tz)

    sessions = (
        (
            await session.execute(
                select(ExerciseLog)
                .where(
                    ExerciseLog.subject == subject,
                    ExerciseLog.planned.is_(False),
                    ExerciseLog.ts >= span_start_utc,
                    ExerciseLog.ts < span_end_utc,
                )
                .order_by(ExerciseLog.ts)
            )
        )
        .scalars()
        .all()
    )
    sessions_by_date: dict[date_type, list[ExerciseLog]] = {}
    for log in sessions:
        day = date_type.fromisoformat(servertime.local_date(tz, log.ts))
        sessions_by_date.setdefault(day, []).append(log)

    rows = []
    for week_start in starts:
        week_end = week_start + timedelta(days=6)
        last_day = min(week_end, today)
        week_sessions = [
            log
            for offset in range((last_day - week_start).days + 1)
            for log in sessions_by_date.get(week_start + timedelta(days=offset), [])
        ]
        strength_sets = [s for log in week_sessions if log.kind == "strength" for s in log.sets]
        rows.append(
            {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "partial": week_end > today,
                "sessions": len(week_sessions),
                "cardio_min": round(
                    sum(
                        float(log.duration_min)
                        for log in week_sessions
                        if log.kind == "cardio" and log.duration_min is not None
                    ),
                    1,
                ),
                "exercise_kcal": round(
                    sum(
                        float(log.kcal_estimate)
                        for log in week_sessions
                        if log.kcal_estimate is not None
                    ),
                    1,
                ),
                "strength_sets": len(strength_sets),
                "strength_volume_kg": round(
                    sum(s.reps * float(s.weight_kg) for s in strength_sets), 1
                ),
            }
        )

    # The movements that actually appear in the window, by the user's own
    # names — the discovery a follow-up `exercise=` call needs, since the
    # catalog is user-grown and nothing else enumerates it.
    seen = {s.exercise.name for log in sessions for s in log.sets if s.exercise is not None}
    names = sorted(seen, key=str.lower)

    movement = None
    if exercise is not None and exercise.strip():
        name = exercise.strip()
        row = await session.scalar(
            select(Exercise).where(
                Exercise.owner_id == subject, func.lower(Exercise.name) == name.lower()
            )
        )
        if row is None:
            raise UnknownExercise(name)

        progression = []
        for log in sessions:
            if log.kind != "strength":
                continue
            own_sets = [s for s in log.sets if s.exercise_id == row.id]
            if not own_sets:
                continue
            loaded = [s for s in own_sets if float(s.weight_kg) > 0]
            top = max(loaded, key=lambda s: _e1rm(s.reps, float(s.weight_kg)), default=None)
            progression.append(
                {
                    "date": servertime.local_date(tz, log.ts),
                    "log_id": log.id,
                    "sets": len(own_sets),
                    "top_set": (
                        {
                            "reps": top.reps,
                            "weight_kg": float(top.weight_kg),
                            "rpe": float(top.rpe) if top.rpe is not None else None,
                        }
                        if top is not None
                        else None
                    ),
                    "e5rm_kg": (
                        round(_e5rm(_e1rm(top.reps, float(top.weight_kg))), 1)
                        if top is not None
                        else None
                    ),
                }
            )
        movement = {"name": row.name, "sessions": progression}

    return {
        "weeks": rows,
        "exercises": names,
        "exercise": movement,
        "server_time": servertime.echo(tz),
    }
