"""Bodyweight upserts and goal phase lifecycles.

What must not regress: one row per subject per day with partial re-logs
merging rather than erasing, and phases that append and close without ever
rewriting what a past day was judged against.
"""

from datetime import date

import pytest

from annos.domain import body as body_domain
from annos.domain import profile as profile_domain
from annos.models import GoalPhase
from conftest import OTHER_SUBJECT, SUBJECT


@pytest.fixture
async def profile(session):
    return await profile_domain.create_profile(session, subject=SUBJECT)


# --- log_weight -----------------------------------------------------------


async def test_log_weight_defaults_to_today_in_the_profile_timezone(session, profile):
    payload = await body_domain.log_weight(session, subject=SUBJECT, weight_kg=82.4)

    assert payload["weight_kg"] == 82.4
    assert payload["date"] == payload["server_time"]["local_date"]


async def test_relogging_a_day_replaces_instead_of_duplicating(session, profile):
    await body_domain.log_weight(session, subject=SUBJECT, weight_kg=82.4, date="2026-08-01")
    payload = await body_domain.log_weight(
        session, subject=SUBJECT, weight_kg=82.0, date="2026-08-01"
    )

    assert payload["weight_kg"] == 82.0


async def test_a_partial_relog_merges_with_the_days_row(session, profile):
    """Morning weight, evening waist: the second write must not erase the first."""
    await body_domain.log_weight(session, subject=SUBJECT, weight_kg=82.4, date="2026-08-01")
    payload = await body_domain.log_weight(
        session, subject=SUBJECT, waist_cm=88.5, date="2026-08-01"
    )

    assert payload["weight_kg"] == 82.4
    assert payload["waist_cm"] == 88.5


async def test_an_empty_measurement_is_refused(session, profile):
    with pytest.raises(body_domain.InvalidMetric, match="nothing to log"):
        await body_domain.log_weight(session, subject=SUBJECT)


@pytest.mark.parametrize("weight", [0, -80, 500])
async def test_impossible_weights_are_refused(session, profile, weight):
    with pytest.raises(body_domain.InvalidMetric, match="out of range"):
        await body_domain.log_weight(session, subject=SUBJECT, weight_kg=weight)


async def test_two_subjects_share_a_date_without_colliding(session, profile):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)

    mine = await body_domain.log_weight(session, subject=SUBJECT, weight_kg=82.4, date="2026-08-01")
    theirs = await body_domain.log_weight(
        session, subject=OTHER_SUBJECT, weight_kg=61.0, date="2026-08-01"
    )

    assert (mine["weight_kg"], theirs["weight_kg"]) == (82.4, 61.0)


# --- set_goal_phase ---------------------------------------------------------


async def test_the_first_phase_opens_with_no_end(session, profile):
    payload = await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2400,
        kcal_rest=2100,
        protein_g=160,
        rate_target=-0.4,
        start_date="2026-08-01",
    )

    assert payload["kind"] == "deficit"
    assert payload["end_date"] is None
    assert payload["closed_previous"] is None


async def test_a_new_phase_closes_the_previous_one_the_day_before(session, profile):
    first = await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2400,
        kcal_rest=2100,
        protein_g=160,
        start_date="2026-07-01",
    )
    second = await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="maintenance",
        kcal_training=2800,
        kcal_rest=2500,
        protein_g=150,
        start_date="2026-08-01",
    )

    assert second["closed_previous"] == {
        "phase_id": first["phase_id"],
        "end_date": "2026-07-31",
    }

    closed = await session.get(GoalPhase, first["phase_id"])
    assert closed.end_date == date(2026, 7, 31)
    assert closed.kcal_target_training == 2400  # closed, never rewritten


async def test_history_evaluates_against_the_phase_in_force_then(session, profile):
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2400,
        kcal_rest=2100,
        protein_g=160,
        start_date="2026-07-01",
    )
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="maintenance",
        kcal_training=2800,
        kcal_rest=2500,
        protein_g=150,
        start_date="2026-08-01",
    )

    july = await body_domain.active_phase(session, subject=SUBJECT, on=date(2026, 7, 15))
    august = await body_domain.active_phase(session, subject=SUBJECT, on=date(2026, 8, 15))
    before = await body_domain.active_phase(session, subject=SUBJECT, on=date(2026, 6, 1))

    assert july.kind == "deficit"
    assert august.kind == "maintenance"
    assert before is None


async def test_a_phase_cannot_start_before_the_current_one(session, profile):
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2400,
        kcal_rest=2100,
        protein_g=160,
        start_date="2026-08-01",
    )

    with pytest.raises(body_domain.InvalidPhase, match="already runs"):
        await body_domain.set_goal_phase(
            session,
            subject=SUBJECT,
            kind="surplus",
            kcal_training=3000,
            kcal_rest=2800,
            protein_g=170,
            start_date="2026-08-01",
        )


@pytest.mark.parametrize(
    ("kind", "rate"),
    [("deficit", 0.4), ("surplus", -0.4), ("maintenance", 0.2), ("deficit", 0)],
)
async def test_a_rate_contradicting_the_kind_is_refused(session, profile, kind, rate):
    """The sign is the kind's meaning: a deficit loses, a surplus gains,
    maintenance holds — a mismatch is a data error, not a preference."""
    with pytest.raises(body_domain.InvalidPhase, match="rate_target"):
        await body_domain.set_goal_phase(
            session,
            subject=SUBJECT,
            kind=kind,
            kcal_training=2400,
            kcal_rest=2100,
            protein_g=160,
            rate_target=rate,
        )


async def test_revising_to_maintenance_requires_clearing_the_rate(session, profile):
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2400,
        kcal_rest=2100,
        protein_g=160,
        rate_target=-0.4,
    )

    with pytest.raises(body_domain.InvalidPhase, match="maintenance"):
        await body_domain.revise_goal_phase(
            session, subject=SUBJECT, changes={"kind": "maintenance"}
        )

    revised = await body_domain.revise_goal_phase(
        session, subject=SUBJECT, changes={"kind": "maintenance", "rate_target": None}
    )
    assert revised["rate_target_kg_per_week"] is None


async def test_nonsense_targets_are_refused(session, profile):
    with pytest.raises(body_domain.InvalidPhase, match="positive"):
        await body_domain.set_goal_phase(
            session, subject=SUBJECT, kind="deficit", kcal_training=0, kcal_rest=2100, protein_g=160
        )
    with pytest.raises(body_domain.InvalidPhase, match="kind"):
        await body_domain.set_goal_phase(
            session, subject=SUBJECT, kind="bulk", kcal_training=3000, kcal_rest=2800, protein_g=170
        )


async def test_phases_are_scoped_by_subject(session, profile):
    """A second user opening a phase must not close the first user's."""
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    mine = await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2400,
        kcal_rest=2100,
        protein_g=160,
    )
    theirs = await body_domain.set_goal_phase(
        session,
        subject=OTHER_SUBJECT,
        kind="surplus",
        kcal_training=3200,
        kcal_rest=2900,
        protein_g=140,
    )

    assert theirs["closed_previous"] is None
    still_open = await session.get(GoalPhase, mine["phase_id"])
    assert still_open.end_date is None


# --- revise_goal_phase -------------------------------------------------------


async def test_revising_the_open_phase_changes_its_targets(session, profile):
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="surplus",
        kcal_training=3000,
        kcal_rest=2800,
        protein_g=170,
        start_date="2026-08-01",
    )

    revised = await body_domain.revise_goal_phase(
        session, subject=SUBJECT, changes={"kind": "deficit", "kcal_rest": 2100}
    )

    assert revised["kind"] == "deficit"
    assert revised["kcal_target_rest"] == 2100
    assert revised["kcal_target_training"] == 3000  # untouched fields stay
    assert revised["end_date"] is None


async def test_moving_the_start_recloses_the_previous_phase(session, profile):
    first = await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2400,
        kcal_rest=2100,
        protein_g=160,
        start_date="2026-07-01",
    )
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="maintenance",
        kcal_training=2800,
        kcal_rest=2500,
        protein_g=150,
        start_date="2026-08-05",
    )

    revised = await body_domain.revise_goal_phase(
        session, subject=SUBJECT, changes={"start_date": "2026-08-01"}
    )

    assert revised["start_date"] == "2026-08-01"
    previous = await session.get(GoalPhase, first["phase_id"])
    assert previous.end_date == date(2026, 7, 31)


async def test_the_open_phase_cannot_move_onto_the_previous_one(session, profile):
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2400,
        kcal_rest=2100,
        protein_g=160,
        start_date="2026-07-01",
    )
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="maintenance",
        kcal_training=2800,
        kcal_rest=2500,
        protein_g=150,
        start_date="2026-08-05",
    )

    with pytest.raises(body_domain.InvalidPhase, match="must start after"):
        await body_domain.revise_goal_phase(
            session, subject=SUBJECT, changes={"start_date": "2026-07-01"}
        )


async def test_revising_with_no_open_phase_is_refused(session, profile):
    with pytest.raises(body_domain.NoOpenPhase):
        await body_domain.revise_goal_phase(session, subject=SUBJECT, changes={"kind": "deficit"})


async def test_revising_unknown_fields_is_refused(session, profile):
    await body_domain.set_goal_phase(
        session, subject=SUBJECT, kind="deficit", kcal_training=2400, kcal_rest=2100, protein_g=160
    )

    with pytest.raises(body_domain.InvalidPhase, match="not revisable"):
        await body_domain.revise_goal_phase(
            session, subject=SUBJECT, changes={"end_date": "2026-08-31"}
        )


async def test_rest_revises_the_open_phase(api, profile):
    await api.post(
        "/api/goals/phase",
        json={"kind": "surplus", "kcal_training": 3000, "kcal_rest": 2800, "protein_g": 170},
    )

    response = await api.patch("/api/goals/phase", json={"changes": {"kind": "maintenance"}})

    assert response.status_code == 200
    assert response.json()["kind"] == "maintenance"


async def test_rest_answers_404_when_nothing_is_open(api, profile):
    response = await api.patch("/api/goals/phase", json={"changes": {"kind": "maintenance"}})

    assert response.status_code == 404


# --- list_goal_phases --------------------------------------------------------


async def test_goal_history_lists_phases_newest_first(session, profile):
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2400,
        kcal_rest=2100,
        protein_g=160,
        rate_target=-0.4,
        start_date="2026-07-01",
    )
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="maintenance",
        kcal_training=2800,
        kcal_rest=2500,
        protein_g=150,
        start_date="2026-08-01",
    )

    payload = await body_domain.list_goal_phases(session, subject=SUBJECT)

    assert [phase["kind"] for phase in payload["phases"]] == ["maintenance", "deficit"]
    current, closed = payload["phases"]
    assert current["end_date"] is None
    assert closed["end_date"] == "2026-07-31"
    assert closed["kcal_target_training"] == 2400
    assert closed["rate_target_kg_per_week"] == -0.4


async def test_goal_history_is_empty_before_any_phase(session, profile):
    payload = await body_domain.list_goal_phases(session, subject=SUBJECT)

    assert payload["phases"] == []
    assert "server_time" in payload


async def test_goal_history_is_scoped_by_subject(session, profile):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    await body_domain.set_goal_phase(
        session,
        subject=OTHER_SUBJECT,
        kind="surplus",
        kcal_training=3200,
        kcal_rest=2900,
        protein_g=140,
    )

    payload = await body_domain.list_goal_phases(session, subject=SUBJECT)

    assert payload["phases"] == []


# --- the two surfaces --------------------------------------------------------


async def test_rest_logs_weight_and_mcp_sees_the_same_day(api, mcp_client, profile):
    """Upsert parity: REST writes, MCP overwrites the same row."""
    response = await api.post("/api/logs/weight", json={"weight_kg": 82.4, "date": "2026-08-01"})
    assert response.status_code == 201

    result = await mcp_client.call_tool("log_weight", {"waist_cm": 88.5, "date": "2026-08-01"})
    payload = result.structured_content

    assert payload["weight_kg"] == 82.4
    assert payload["waist_cm"] == 88.5


async def test_rest_rejects_an_empty_weight_log(api, profile):
    response = await api.post("/api/logs/weight", json={})
    assert response.status_code == 422


async def test_rest_sets_a_goal_phase(api, profile):
    response = await api.post(
        "/api/goals/phase",
        json={"kind": "deficit", "kcal_training": 2400, "kcal_rest": 2100, "protein_g": 160},
    )
    assert response.status_code == 201
    assert response.json()["end_date"] is None


async def test_rest_lists_the_goal_history(api, profile):
    for start, kind in (("2026-07-01", "deficit"), ("2026-08-01", "maintenance")):
        await api.post(
            "/api/goals/phase",
            json={
                "kind": kind,
                "kcal_training": 2400,
                "kcal_rest": 2100,
                "protein_g": 160,
                "start_date": start,
            },
        )

    response = await api.get("/api/goals/phases")

    assert response.status_code == 200
    phases = response.json()["phases"]
    assert [phase["kind"] for phase in phases] == ["maintenance", "deficit"]
    assert phases[0]["end_date"] is None
    assert phases[1]["end_date"] == "2026-07-31"
