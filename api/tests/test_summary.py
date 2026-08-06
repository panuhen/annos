"""daily_summary: the whole day in one call, against the target in force.

What must not regress: no-args means today as the server defines it, planned
entries visible but never counted, targets resolved from the phase active on
*that* day, and the honest "rest day" label while exercise logging doesn't
exist yet.
"""

import pytest

from annos.domain import body as body_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.domain import summary as summary_domain
from conftest import SUBJECT


@pytest.fixture
async def profile(session):
    return await profile_domain.create_profile(session, subject=SUBJECT)


@pytest.fixture
async def deficit_phase(session, profile):
    return await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2400,
        kcal_rest=2100,
        protein_g=160,
        rate_target=-0.4,
        start_date="2026-07-01",
    )


async def test_no_arguments_means_today(session, profile):
    summary = await summary_domain.daily_summary(session, subject=SUBJECT)

    assert summary["date"] == summary["server_time"]["local_date"]
    assert summary["totals"]["items_logged"] == 0
    assert summary["meals"] == []


async def test_totals_target_and_remaining_line_up(session, deficit_phase, make_food):
    food = await make_food(name_en="lunch bowl", kcal=550, protein_g=35, carbs_g=50, fat_g=20)
    await meals_domain.log_meal(
        session,
        subject=SUBJECT,
        items=[{"food_id": food.id, "grams": 100}],
        meal="lunch",
        ts="2026-08-03T12:40",
    )

    summary = await summary_domain.daily_summary(session, subject=SUBJECT, date="2026-08-03")

    assert summary["totals"]["kcal"] == pytest.approx(550.0)
    assert summary["target"] == {
        "kind": "deficit",
        "kcal": 2100,  # rest-day target: no exercise logging yet
        "protein_g": 160,
        "rate_kg_per_week": -0.4,
    }
    assert summary["remaining"]["kcal"] == pytest.approx(1550.0)
    assert summary["remaining"]["protein_g"] == pytest.approx(125.0)
    assert summary["day_type"] == "rest"

    (meal,) = summary["meals"]
    assert meal["meal"] == "lunch"
    assert meal["kcal"] == pytest.approx(550.0)
    assert meal["log_id"]  # enough to hand straight to revise_log

    # Items ride along: the day view lists what was eaten, and a client
    # revising a log it didn't create sees its current contents.
    (item,) = meal["items"]
    assert item["food_id"] == food.id
    assert item["name"] == "lunch bowl"
    assert item["source"] == "fineli"
    assert item["grams"] == pytest.approx(100.0)
    assert item["kcal"] == pytest.approx(550.0)


async def test_going_over_target_goes_negative_not_clamped(session, deficit_phase, make_food):
    food = await make_food(name_en="feast", kcal=800, protein_g=30, carbs_g=80, fat_g=40)
    await meals_domain.log_meal(
        session,
        subject=SUBJECT,
        items=[{"food_id": food.id, "grams": 300}],
        ts="2026-08-03T20:00",
    )

    summary = await summary_domain.daily_summary(session, subject=SUBJECT, date="2026-08-03")

    assert summary["remaining"]["kcal"] == pytest.approx(-300.0)


async def test_without_a_phase_there_is_no_target(session, profile, make_food):
    food = await make_food(name_en="bread", kcal=250, protein_g=8, carbs_g=45, fat_g=3)
    await meals_domain.log_meal(
        session, subject=SUBJECT, items=[{"food_id": food.id, "grams": 100}]
    )

    summary = await summary_domain.daily_summary(session, subject=SUBJECT)

    assert summary["target"] is None
    assert summary["remaining"] is None
    assert summary["totals"]["kcal"] == pytest.approx(250.0)


async def test_a_past_day_is_judged_by_the_phase_active_then(session, deficit_phase, make_food):
    """Setting a new phase must not rewrite what July was measured against."""
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="maintenance",
        kcal_training=2900,
        kcal_rest=2600,
        protein_g=150,
        start_date="2026-08-01",
    )

    july = await summary_domain.daily_summary(session, subject=SUBJECT, date="2026-07-15")
    august = await summary_domain.daily_summary(session, subject=SUBJECT, date="2026-08-15")

    assert july["target"]["kcal"] == 2100
    assert august["target"]["kcal"] == 2600


async def test_planned_meals_are_listed_but_not_counted(session, deficit_phase, make_food):
    food = await make_food(name_en="planned dinner", kcal=600, protein_g=40, carbs_g=50, fat_g=25)
    await meals_domain.log_meal(
        session,
        subject=SUBJECT,
        items=[{"food_id": food.id, "grams": 100}],
        input_mode="plan",
        ts="2026-08-03T18:00",
    )

    summary = await summary_domain.daily_summary(session, subject=SUBJECT, date="2026-08-03")

    assert summary["totals"]["kcal"] == pytest.approx(0.0)
    (meal,) = summary["meals"]
    assert meal["planned"] is True
    assert meal["kcal"] == pytest.approx(600.0)


async def test_profile_context_rides_along_verbatim(session, profile):
    await profile_domain.update_profile(
        session,
        subject=SUBJECT,
        changes={"coaching_notes": "be blunt", "dietary_prefs": {"no": ["pork"]}},
    )

    summary = await summary_domain.daily_summary(session, subject=SUBJECT)

    assert summary["profile_context"] == {
        "dietary_prefs": {"no": ["pork"]},
        "coaching_notes": "be blunt",
    }


async def test_the_two_surfaces_agree(api, mcp_client, deficit_phase, make_food, session):
    food = await make_food(name_en="parity oats", kcal=370, protein_g=13, carbs_g=60, fat_g=7)
    await meals_domain.log_meal(
        session,
        subject=SUBJECT,
        items=[{"food_id": food.id, "grams": 50}],
        ts="2026-08-03T08:00",
    )

    rest = (await api.get("/api/summary/daily", params={"date": "2026-08-03"})).json()
    mcp = (await mcp_client.call_tool("daily_summary", {"date": "2026-08-03"})).structured_content

    # server_time differs by the clock between the two calls; everything else
    # must be byte-identical.
    rest.pop("server_time")
    mcp.pop("server_time")
    assert rest == mcp


async def test_a_malformed_date_is_a_422_not_a_500(api, profile):
    response = await api.get("/api/summary/daily", params={"date": "yesterday"})
    assert response.status_code == 422
