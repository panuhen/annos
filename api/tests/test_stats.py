"""The stats views: measured TDEE, the weekly ledger, weight and training trends.

What must not regress: the TDEE arithmetic against hand-computed cases and its
refusal paths (null with reasons, never a formula guess); smoothing that spans
gaps by shrinking the divisor rather than fabricating values; the ledger
judging every day against the phase and day type in force *then*; and the
e5RM trend excluding bodyweight sets instead of estimating a load that was
never stated.
"""

from datetime import date, timedelta

import pytest

from annos import servertime
from annos.domain import body as body_domain
from annos.domain import days as days_domain
from annos.domain import exercise as exercise_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.domain import stats as stats_domain
from annos.models import Activity
from conftest import SUBJECT

TZ = "Europe/Helsinki"


@pytest.fixture
async def profile(session):
    return await profile_domain.create_profile(session, subject=SUBJECT)


@pytest.fixture
async def aged_profile(session, profile):
    """A profile old enough for the TDEE window — a fresh account refuses with
    insufficient_history by design, so most TDEE tests need this."""
    profile.created_at = servertime.now() - timedelta(days=40)
    await session.commit()
    return profile


def local_today() -> date:
    return date.fromisoformat(servertime.local_date(TZ))


async def weigh(session, day: date, kg: float) -> None:
    await body_domain.log_weight(session, subject=SUBJECT, weight_kg=kg, date=day.isoformat())


async def eat(session, food, day: date, grams: float = 100) -> None:
    await meals_domain.log_meal(
        session,
        subject=SUBJECT,
        items=[{"food_id": food.id, "grams": grams}],
        ts=f"{day.isoformat()}T12:00",
    )


def previous_week_monday() -> date:
    """The Monday of the last *complete* ISO week — tests stay day-agnostic."""
    today = local_today()
    return today - timedelta(days=today.weekday()) - timedelta(weeks=1)


# --- weight_history -----------------------------------------------------------


async def test_weight_series_smoothed_trend_and_rate(session, profile):
    """Linear data makes the smoothing auditable by hand: the trailing 7-day
    mean of a straight line is the line three days back, and a 0.05 kg/day
    slope reads as −0.35 kg/week."""
    today = local_today()
    for back in range(21):
        await weigh(session, today - timedelta(days=back), 84.0 + 0.05 * back)

    history = await stats_domain.weight_history(session, subject=SUBJECT, days=21)

    assert [p["date"] for p in history["points"]] == [
        (today - timedelta(days=back)).isoformat() for back in range(20, -1, -1)
    ]
    assert history["points"][-1]["weight_kg"] == pytest.approx(84.0)
    assert history["smoothed"][-1]["weight_kg"] == pytest.approx(84.15)  # the line, 3 days back
    assert history["rate_kg_per_week"] == pytest.approx(-0.35)


async def test_smoothing_spans_gaps_and_waist_days_carry_no_weight(session, profile):
    """Two weigh-ins in a week smooth over two values, not seven; a waist-only
    day is a point but never a smoothed value; a rate whose anchor week holds
    no weigh-in is null, not extrapolated."""
    today = local_today()
    await weigh(session, today - timedelta(days=10), 80.0)
    await weigh(session, today - timedelta(days=8), 81.0)
    await body_domain.log_weight(session, subject=SUBJECT, waist_cm=90.0, date=today.isoformat())

    history = await stats_domain.weight_history(session, subject=SUBJECT, days=30)

    assert len(history["points"]) == 3
    assert history["points"][-1]["weight_kg"] is None
    assert history["points"][-1]["waist_cm"] == pytest.approx(90.0)
    assert [s["weight_kg"] for s in history["smoothed"]] == [
        pytest.approx(80.0),
        pytest.approx(80.5),
    ]
    assert history["rate_kg_per_week"] is None


async def test_weight_history_window_bounds(session, profile):
    with pytest.raises(stats_domain.InvalidQuery):
        await stats_domain.weight_history(session, subject=SUBJECT, days=0)
    with pytest.raises(stats_domain.InvalidQuery):
        await stats_domain.weight_history(session, subject=SUBJECT, days=366)


# --- get_tdee -----------------------------------------------------------------


async def test_tdee_refuses_honestly_on_a_fresh_account(session, profile):
    """No data means null with machine-readable reasons and the progress
    toward enough — never a formula guess."""
    tdee = await stats_domain.get_tdee(session, subject=SUBJECT)

    assert tdee["tdee_kcal"] is None
    assert tdee["confidence"] is None
    assert set(tdee["reasons"]) == {
        "insufficient_history",
        "insufficient_logging",
        "insufficient_weight_data",
    }
    assert tdee["coverage"] == {"logged_days": 0, "required_days": 17, "weigh_in_days": 0}
    assert tdee["window"]["days"] == 21


async def test_tdee_matches_hand_arithmetic(session, aged_profile, make_food):
    """2000 kcal/day intake while losing 1.0 kg over the 21-day window:
    TDEE = 2000 − (−1.0 × 7700) / 21 ≈ 2367, full coverage, confidence ok."""
    food = await make_food(name_en="ration", kcal=2000, protein_g=100)
    today = local_today()
    end = today - timedelta(days=1)
    start = end - timedelta(days=20)

    for offset in range(21):
        await eat(session, food, start + timedelta(days=offset))
    # Weights from a week before the window so both smoothed endpoints exist;
    # −0.05 kg/day makes the smoothed change exactly −1.0 kg across 20 days.
    first_weigh = start - timedelta(days=6)
    for offset in range(27):
        await weigh(session, first_weigh + timedelta(days=offset), 86.0 - 0.05 * offset)

    tdee = await stats_domain.get_tdee(session, subject=SUBJECT)

    assert tdee["tdee_kcal"] == 2367
    assert tdee["confidence"] == "ok"
    assert tdee["reasons"] == []
    assert tdee["coverage"]["logged_days"] == 21
    assert tdee["inputs"]["intake_avg_kcal"] == pytest.approx(2000.0)
    assert tdee["inputs"]["weight_change_kg"] == pytest.approx(-1.0)
    assert tdee["window"] == {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": 21,
    }


async def test_tdee_flags_its_weaknesses_instead_of_hiding_them(session, aged_profile, make_food):
    """Marginal logging, sparse weigh-ins and a phase newer than the window
    each flag the estimate low-confidence — the number is still returned."""
    food = await make_food(name_en="ration", kcal=1800)
    today = local_today()
    end = today - timedelta(days=1)
    start = end - timedelta(days=20)

    for offset in range(17):  # exactly the 80 % floor, below the 90 % comfort line
        await eat(session, food, start + timedelta(days=offset))
    first_weigh = start - timedelta(days=6)
    for offset in range(0, 27, 3):  # every third day: 7 weigh-ins inside the window
        await weigh(session, first_weigh + timedelta(days=offset), 85.0 - 0.05 * offset)
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2200,
        kcal_rest=1800,
        protein_training=150,
        protein_rest=130,
        rate_target=-0.5,
        start_date=(today - timedelta(days=5)).isoformat(),
    )

    tdee = await stats_domain.get_tdee(session, subject=SUBJECT)

    assert tdee["tdee_kcal"] is not None
    assert tdee["confidence"] == "low"
    assert set(tdee["reasons"]) == {
        "new_phase_water_shift",
        "marginal_logging",
        "sparse_weigh_ins",
    }
    assert tdee["coverage"]["logged_days"] == 17
    assert tdee["coverage"]["weigh_in_days"] == 7


# --- weekly_review --------------------------------------------------------------


async def test_the_ledger_judges_each_day_against_its_own_target(session, profile, make_food):
    """A rest day and a derived training day in the same week average their
    *own* targets; a manual mark then re-judges the day both ways."""
    rest_food = await make_food(name_en="rest ration", kcal=1800, protein_g=100)
    training_food = await make_food(name_en="training ration", kcal=2200, protein_g=100)
    monday = previous_week_monday()
    tuesday = monday + timedelta(days=1)
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2200,
        kcal_rest=1800,
        protein_training=150,
        protein_rest=130,
        start_date=(monday - timedelta(days=14)).isoformat(),
    )
    await eat(session, rest_food, monday)
    await eat(session, training_food, tuesday)
    await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="cardio",
        duration_min=30,
        ts=f"{tuesday.isoformat()}T17:00",
    )

    review = await stats_domain.weekly_review(session, subject=SUBJECT, weeks=2)

    week = review["weeks"][1]  # newest first: [0] is the current, partial week
    assert week["week_start"] == monday.isoformat()
    assert week["partial"] is False
    assert week["days_in_week"] == 7
    assert week["days_logged"] == 2
    assert week["kcal_avg"] == pytest.approx(2000.0)
    # Monday rest (1800), Tuesday derived training (2200) — judged per day.
    assert week["kcal_target_avg"] == pytest.approx(2000.0)
    assert week["kcal_delta_avg"] == pytest.approx(0.0)
    assert week["targeted_days"] == 2
    assert week["protein_avg_g"] == pytest.approx(100.0)
    assert week["protein_target_avg_g"] == pytest.approx(140.0)
    assert week["sessions"] == 1
    assert review["active_phase"]["kind"] == "deficit"

    # The user says Tuesday was a rest day: the mark beats the derivation and
    # the same intake is now 400 over target on that day.
    await days_domain.set_day_type(
        session, subject=SUBJECT, day_type="rest", date=tuesday.isoformat()
    )
    review = await stats_domain.weekly_review(session, subject=SUBJECT, weeks=2)

    week = review["weeks"][1]
    assert week["kcal_target_avg"] == pytest.approx(1800.0)
    assert week["kcal_delta_avg"] == pytest.approx(200.0)


async def test_days_before_any_phase_have_no_target(session, profile, make_food):
    """Untargeted days stay out of the target average and are counted
    honestly — an average against a target that didn't exist would be
    fiction."""
    food = await make_food(name_en="ration", kcal=1800)
    await eat(session, food, previous_week_monday())

    review = await stats_domain.weekly_review(session, subject=SUBJECT, weeks=2)

    week = review["weeks"][1]
    assert week["days_logged"] == 1
    assert week["kcal_avg"] == pytest.approx(1800.0)
    assert week["kcal_target_avg"] is None
    assert week["kcal_delta_avg"] is None
    assert week["targeted_days"] == 0
    assert review["active_phase"] is None
    # The TDEE block rides along, refusing for its own honest reasons.
    assert review["tdee"]["tdee_kcal"] is None


# --- training_history -----------------------------------------------------------


@pytest.fixture
async def running(session):
    activity = Activity(code="12030", name="Running, general", category="running", met=8.0)
    session.add(activity)
    await session.commit()
    return activity


async def test_weekly_training_facts_and_e5rm_progression(session, profile, running):
    """Volume is reps × kg over every set; the e5RM of a 5-rep set is its own
    weight (Epley round-trips), which makes the trend auditable by hand."""
    monday = previous_week_monday()
    await weigh(session, monday - timedelta(days=1), 80.0)
    await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="strength",
        ts=f"{(monday + timedelta(days=1)).isoformat()}T17:00",
        sets=[
            {"exercise": "Bench Press", "reps": 5, "weight_kg": 100, "rpe": 8},
            {"exercise": "Bench Press", "reps": 8, "weight_kg": 80},
        ],
    )
    await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="cardio",
        activity_id=running.id,
        duration_min=45,
        ts=f"{(monday + timedelta(days=2)).isoformat()}T08:00",
    )

    history = await stats_domain.training_history(
        session, subject=SUBJECT, exercise="bench press", weeks=2
    )

    week = history["weeks"][1]
    assert week["sessions"] == 2
    assert week["cardio_min"] == pytest.approx(45.0)
    assert week["exercise_kcal"] == pytest.approx(480.0)  # 8.0 MET × 80 kg × 0.75 h
    assert week["strength_sets"] == 2
    assert week["strength_volume_kg"] == pytest.approx(1140.0)  # 5×100 + 8×80

    # The window's movements ride along by the user's own names — the only
    # enumeration of a user-grown catalog, for selectors and follow-up calls.
    assert history["exercises"] == ["Bench Press"]

    movement = history["exercise"]
    assert movement["name"] == "Bench Press"  # matched case-insensitively, answered as logged
    (session_row,) = movement["sessions"]
    assert session_row["sets"] == 2
    assert session_row["top_set"] == {"reps": 5, "weight_kg": 100.0, "rpe": 8.0}
    assert session_row["e5rm_kg"] == pytest.approx(100.0)


async def test_bodyweight_sets_carry_no_e5rm(session, profile):
    """Weight 0 is a bodyweight set: it counts as work but carries no load to
    estimate, so the session reports null rather than a fabricated number."""
    monday = previous_week_monday()
    await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="strength",
        ts=f"{monday.isoformat()}T17:00",
        sets=[{"exercise": "Pull-up", "reps": 10, "weight_kg": 0}],
    )

    history = await stats_domain.training_history(
        session, subject=SUBJECT, exercise="pull-up", weeks=2
    )

    assert history["weeks"][1]["strength_volume_kg"] == pytest.approx(0.0)
    (session_row,) = history["exercise"]["sessions"]
    assert session_row["sets"] == 1
    assert session_row["top_set"] is None
    assert session_row["e5rm_kg"] is None


async def test_unknown_exercise_is_an_error_not_a_guess(session, profile):
    with pytest.raises(stats_domain.UnknownExercise):
        await stats_domain.training_history(session, subject=SUBJECT, exercise="benchh press")
