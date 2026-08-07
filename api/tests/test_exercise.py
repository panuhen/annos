"""Exercise logging: sessions, sets, MET arithmetic, day-type derivation.

What must not regress: the kcal estimate comes from the bodyweight snapshot
taken at log time (never today's weight), degrades to NULL instead of
fabricating, strength movements stay scoped to their owner, and a non-planned
session derives a training day that the user's own mark still overrides.
"""

from datetime import date, timedelta

import pytest

from annos import servertime
from annos.domain import body as body_domain
from annos.domain import days as days_domain
from annos.domain import exercise as exercise_domain
from annos.domain import profile as profile_domain
from annos.domain import summary as summary_domain
from annos.models import Activity, Exercise
from conftest import OTHER_SUBJECT, SUBJECT

TZ = "Europe/Helsinki"


@pytest.fixture
async def profile(session):
    return await profile_domain.create_profile(session, subject=SUBJECT)


@pytest.fixture
def make_activity(session):
    async def _make(name: str, met: float, category: str = "Sports", code: str | None = None):
        activity = Activity(
            code=code or str(90000 + hash(name) % 9999).zfill(5),
            name=name,
            category=category,
            met=met,
        )
        session.add(activity)
        await session.commit()
        return activity

    return _make


def local_today() -> date:
    return date.fromisoformat(servertime.local_date(TZ))


# --- find_activity -----------------------------------------------------------


async def test_find_activity_substring_qualifies_and_plain_word_ranks_first(
    session, profile, make_activity
):
    """The melon lesson applied from day one: a short query must match long
    Compendium compounds, and the plain activity outranks them."""
    await make_activity("Running, 6-6.3 mph (10 min/mile)", 9.3, code="12050")
    await make_activity("Running (Taylor Code 200)", 8.0, code="12150")
    await make_activity("Water aerobics, water calisthenics", 5.5, code="18355")

    results = await exercise_domain.find_activity(session, subject=SUBJECT, query="running")

    assert [r["name"] for r in results][:2] == [
        "Running (Taylor Code 200)",
        "Running, 6-6.3 mph (10 min/mile)",
    ]
    assert results[0]["met"] == 8.0


async def test_find_activity_forgives_typos(session, profile, make_activity):
    await make_activity("Bicycling, general", 7.0, code="01014")

    results = await exercise_domain.find_activity(session, subject=SUBJECT, query="bicylcing")

    assert results and results[0]["name"] == "Bicycling, general"


# --- the estimate ------------------------------------------------------------


async def test_cardio_estimate_is_met_times_weight_times_hours(session, profile, make_activity):
    activity = await make_activity("Running (Taylor Code 200)", 8.0)
    await body_domain.log_weight(session, subject=SUBJECT, weight_kg=80)

    log = await exercise_domain.log_exercise(
        session, subject=SUBJECT, kind="cardio", activity_id=activity.id, duration_min=45
    )

    # 8.0 MET x 80 kg x 0.75 h = 480 kcal
    assert log["kcal_estimate"] == pytest.approx(480.0)
    assert log["activity"]["name"] == "Running (Taylor Code 200)"
    assert log["duration_min"] == pytest.approx(45.0)


async def test_no_weight_ever_logged_means_null_not_a_fabrication(session, profile, make_activity):
    activity = await make_activity("Running (Taylor Code 200)", 8.0)

    log = await exercise_domain.log_exercise(
        session, subject=SUBJECT, kind="cardio", activity_id=activity.id, duration_min=45
    )

    assert log["kcal_estimate"] is None


async def test_strength_gets_the_flat_met_over_its_duration(session, profile):
    await body_domain.log_weight(session, subject=SUBJECT, weight_kg=80)

    log = await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="strength",
        duration_min=60,
        sets=[{"exercise": "Bench Press", "reps": 5, "weight_kg": 100}],
    )

    # flat 5.0 MET x 80 kg x 1 h
    assert log["kcal_estimate"] == pytest.approx(400.0)


async def test_the_estimate_rescales_from_the_log_time_weight_not_todays(
    session, profile, make_activity
):
    """The snapshot discipline: a later weight change must not rewrite what
    the session was computed from."""
    activity = await make_activity("Running (Taylor Code 200)", 8.0)
    await body_domain.log_weight(
        session, subject=SUBJECT, weight_kg=80, date=(local_today() - timedelta(days=1)).isoformat()
    )
    log = await exercise_domain.log_exercise(
        session, subject=SUBJECT, kind="cardio", activity_id=activity.id, duration_min=30
    )
    assert log["kcal_estimate"] == pytest.approx(320.0)

    # The user then logs a very different weight...
    await body_domain.log_weight(session, subject=SUBJECT, weight_kg=100)
    # ...and corrects the duration. The estimate must use the 80 kg snapshot.
    revised = await exercise_domain.revise_exercise(
        session, subject=SUBJECT, log_id=log["log_id"], changes={"duration_min": 60}
    )

    assert revised["kcal_estimate"] == pytest.approx(640.0)  # 8 x 80 x 1, not 8 x 100 x 1


# --- strength sets and the owner-scoped catalog ------------------------------


async def test_sets_create_movements_once_and_match_case_insensitively(session, profile):
    first = await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="strength",
        sets=[
            {"exercise": "Penkki", "reps": 5, "weight_kg": 100, "rpe": 8},
            {"exercise": "penkki", "reps": 5, "weight_kg": 102.5},
            {"exercise": "Maastaveto", "reps": 3, "weight_kg": 140},
        ],
    )

    assert [s["set_no"] for s in first["sets"]] == [1, 2, 3]
    assert first["sets"][0]["exercise"] == "Penkki"
    assert first["sets"][1]["exercise"] == "Penkki"  # matched, not re-created

    rows = (await session.scalars(Exercise.__table__.select())).all()
    assert len(rows) == 2


async def test_movements_are_scoped_to_their_owner(session, profile):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    await exercise_domain.log_exercise(
        session,
        subject=OTHER_SUBJECT,
        kind="strength",
        sets=[{"exercise": "Penkki", "reps": 5, "weight_kg": 60}],
    )
    await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="strength",
        sets=[{"exercise": "Penkki", "reps": 5, "weight_kg": 100}],
    )

    rows = (await session.execute(Exercise.__table__.select())).all()
    assert len(rows) == 2  # one per owner — no sharing, no leaking


async def test_a_bodyweight_set_is_weight_zero_not_missing(session, profile):
    log = await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="strength",
        sets=[{"exercise": "Pull-up", "reps": 10, "weight_kg": 0}],
    )

    assert log["sets"][0]["weight_kg"] == 0.0


# --- shapes that make no sense fail loudly -----------------------------------


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"kind": "run"}, "kind"),
        ({"kind": "cardio", "sets": [{"exercise": "x", "reps": 1, "weight_kg": 1}]}, "strength"),
        ({"kind": "strength", "activity_id": 1}, "sets, not a catalog activity"),
        ({"kind": "cardio"}, "empty session"),
        ({"kind": "cardio", "duration_min": -5}, "positive"),
        ({"kind": "strength", "sets": [{"exercise": "x", "reps": 0, "weight_kg": 1}]}, "reps"),
        (
            {"kind": "strength", "sets": [{"exercise": "x", "reps": 1, "weight_kg": 1, "rpe": 11}]},
            "rpe",
        ),
        ({"kind": "other", "duration_min": 30, "source": "guess"}, "source"),
    ],
)
async def test_invalid_shapes_are_refused(session, profile, kwargs, match):
    with pytest.raises(exercise_domain.InvalidExercise, match=match):
        await exercise_domain.log_exercise(session, subject=SUBJECT, **kwargs)


async def test_an_unknown_activity_is_refused(session, profile):
    with pytest.raises(exercise_domain.UnknownActivity):
        await exercise_domain.log_exercise(
            session, subject=SUBJECT, kind="cardio", activity_id=99999, duration_min=30
        )


# --- day-type derivation -----------------------------------------------------


async def test_a_session_derives_a_training_day(session, profile):
    log = await exercise_domain.log_exercise(
        session, subject=SUBJECT, kind="strength", duration_min=60, notes="gym"
    )

    assert (log["day_type"], log["day_type_source"]) == ("training", "derived")

    day_type, source = await days_domain.resolve_day_type(
        session, subject=SUBJECT, on=local_today(), tz=TZ
    )
    assert (day_type, source) == ("training", "derived")


async def test_a_planned_session_derives_nothing(session, profile):
    log = await exercise_domain.log_exercise(
        session, subject=SUBJECT, kind="cardio", duration_min=30, notes="evening run", planned=True
    )

    assert (log["day_type"], log["day_type_source"]) == ("rest", "default")


async def test_the_users_mark_beats_the_derivation(session, profile):
    await days_domain.set_day_type(session, subject=SUBJECT, day_type="rest")
    log = await exercise_domain.log_exercise(
        session, subject=SUBJECT, kind="cardio", duration_min=20, notes="easy walk"
    )

    assert (log["day_type"], log["day_type_source"]) == ("rest", "manual")


async def test_deleting_the_only_session_falls_back_to_rest(session, profile):
    log = await exercise_domain.log_exercise(
        session, subject=SUBJECT, kind="strength", duration_min=45, notes="gym"
    )

    gone = await exercise_domain.delete_exercise(session, subject=SUBJECT, log_id=log["log_id"])

    assert (gone["day_type"], gone["day_type_source"]) == ("rest", "default")


async def test_derivation_respects_the_local_day_boundary(session, profile):
    """A 00:30 session belongs to the new local day, same rule as meals."""
    today = local_today()
    await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="cardio",
        duration_min=30,
        notes="night ride",
        ts=f"{today.isoformat()}T00:30",
    )

    day_type, source = await days_domain.resolve_day_type(session, subject=SUBJECT, on=today, tz=TZ)
    yesterday_type, yesterday_source = await days_domain.resolve_day_type(
        session, subject=SUBJECT, on=today - timedelta(days=1), tz=TZ
    )

    assert (day_type, source) == ("training", "derived")
    assert (yesterday_type, yesterday_source) == ("rest", "default")


# --- revision and deletion ---------------------------------------------------


async def test_sets_replace_the_whole_list(session, profile):
    log = await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="strength",
        sets=[
            {"exercise": "Penkki", "reps": 5, "weight_kg": 100},
            {"exercise": "Kyykky", "reps": 5, "weight_kg": 120},
        ],
    )

    revised = await exercise_domain.revise_exercise(
        session,
        subject=SUBJECT,
        log_id=log["log_id"],
        changes={"sets": [{"exercise": "Penkki", "reps": 5, "weight_kg": 105}]},
    )

    assert len(revised["sets"]) == 1
    assert revised["sets"][0]["weight_kg"] == 105.0


async def test_confirming_a_planned_session_starts_deriving(session, profile):
    log = await exercise_domain.log_exercise(
        session, subject=SUBJECT, kind="cardio", duration_min=30, notes="run", planned=True
    )
    assert log["day_type"] == "rest"

    confirmed = await exercise_domain.revise_exercise(
        session, subject=SUBJECT, log_id=log["log_id"], changes={"planned": False}
    )

    assert (confirmed["day_type"], confirmed["day_type_source"]) == ("training", "derived")


async def test_unknown_changes_fail_loudly(session, profile):
    log = await exercise_domain.log_exercise(
        session, subject=SUBJECT, kind="other", duration_min=30, notes="sauna"
    )

    with pytest.raises(exercise_domain.InvalidExercise, match="not revisable"):
        await exercise_domain.revise_exercise(
            session, subject=SUBJECT, log_id=log["log_id"], changes={"kcal_estimate": 900}
        )


async def test_another_subjects_log_is_not_found(session, profile):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    log = await exercise_domain.log_exercise(
        session, subject=OTHER_SUBJECT, kind="other", duration_min=30, notes="theirs"
    )

    with pytest.raises(exercise_domain.ExerciseLogNotFound):
        await exercise_domain.delete_exercise(session, subject=SUBJECT, log_id=log["log_id"])


# --- the summary and the two surfaces ----------------------------------------


async def test_the_days_sessions_ride_in_the_summary(session, profile, make_activity):
    activity = await make_activity("Running (Taylor Code 200)", 8.0)
    await body_domain.log_weight(session, subject=SUBJECT, weight_kg=80)
    await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="cardio",
        activity_id=activity.id,
        duration_min=30,
        notes="tempo",
    )

    summary = await summary_domain.daily_summary(session, subject=SUBJECT)

    (ex,) = summary["exercise"]
    assert ex["activity"]["name"] == "Running (Taylor Code 200)"
    assert ex["activity"]["met"] == 8.0
    assert ex["kcal_estimate"] == pytest.approx(320.0)
    assert ex["sets"] == []
    assert summary["day_type"] == "training"
    assert summary["day_type_source"] == "derived"


async def test_the_two_surfaces_agree(api, mcp_client, session, profile, make_activity):
    activity = await make_activity("Running (Taylor Code 200)", 8.0)
    await body_domain.log_weight(session, subject=SUBJECT, weight_kg=80)

    logged = await mcp_client.call_tool(
        "log_exercise",
        {"kind": "cardio", "activity_id": activity.id, "duration_min": 45, "notes": "parity run"},
    )
    assert logged.structured_content["kcal_estimate"] == pytest.approx(480.0)

    rest = (await api.get("/api/summary/daily")).json()
    mcp = (await mcp_client.call_tool("daily_summary")).structured_content

    rest.pop("server_time")
    mcp.pop("server_time")
    assert rest == mcp
    assert rest["exercise"][0]["notes"] == "parity run"


async def test_activity_search_agrees_across_surfaces(api, mcp_client, profile, make_activity):
    await make_activity("Running (Taylor Code 200)", 8.0)

    rest = (await api.get("/api/activities/search", params={"q": "running"})).json()
    mcp = (await mcp_client.call_tool("find_activity", {"query": "running"})).structured_content

    assert rest["results"] == mcp["results"]


async def test_rest_validates_the_obvious(api, profile):
    assert (
        await api.post("/api/logs/exercise", json={"kind": "cardio", "duration_min": -5})
    ).status_code == 422
    assert (
        await api.post("/api/logs/exercise", json={"kind": "run", "duration_min": 30})
    ).status_code == 422
    assert (await api.delete("/api/logs/exercise/12345")).status_code == 404
