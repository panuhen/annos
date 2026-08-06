"""The core loop: log a meal, get the day's totals back, correct it later.

The details that matter here are the ones that silently corrupt history or
mix users if they regress: macro snapshots surviving food edits, the day
boundary living in the profile timezone, naive backdating timestamps read in
that timezone, and every query scoped by subject.
"""

from datetime import UTC, datetime

import pytest

from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.models import Food, MealLog
from conftest import OTHER_SUBJECT, SUBJECT


@pytest.fixture
async def profile(session):
    """The logging subject. Timezone defaults to Europe/Helsinki, which the
    day-boundary tests below rely on."""
    return await profile_domain.create_profile(session, subject=SUBJECT)


async def log(session, **kwargs):
    kwargs.setdefault("subject", SUBJECT)
    return await meals_domain.log_meal(session, **kwargs)


async def test_log_meal_returns_the_meal_and_day_totals(session, profile, make_food):
    porridge = await make_food(name_fi="kaurapuuro", kcal=60, protein_g=2, carbs_g=10, fat_g=1)

    payload = await log(session, items=[{"food_id": porridge.id, "grams": 300}], meal="breakfast")

    assert payload["meal"] == "breakfast"
    assert payload["planned"] is False
    (item,) = payload["items"]
    assert item["kcal"] == pytest.approx(180.0)
    assert item["protein_g"] == pytest.approx(6.0)
    assert payload["day_totals"]["kcal"] == pytest.approx(180.0)
    assert payload["day_totals"]["items_logged"] == 1
    assert payload["server_time"]["timezone"] == "Europe/Helsinki"


async def test_totals_accumulate_within_the_day(session, profile, make_food):
    food = await make_food(name_en="bread", kcal=250, protein_g=8, carbs_g=45, fat_g=3)

    await log(session, items=[{"food_id": food.id, "grams": 100}])
    payload = await log(session, items=[{"food_id": food.id, "grams": 100}])

    assert payload["day_totals"]["kcal"] == pytest.approx(500.0)
    assert payload["day_totals"]["items_logged"] == 2


async def test_the_snapshot_survives_a_food_edit(session, profile, make_food):
    """Food definitions change; history must not."""
    food = await make_food(name_en="yogurt", kcal=100, protein_g=10, carbs_g=4, fat_g=2)
    payload = await log(session, items=[{"food_id": food.id, "grams": 200}])

    row = await session.get(Food, food.id)
    row.kcal = 999
    await session.commit()

    totals = await meals_domain.day_totals(
        session,
        subject=SUBJECT,
        local_date=payload["day_totals"]["local_date"],
        tz="Europe/Helsinki",
    )
    assert totals["kcal"] == pytest.approx(200.0)


async def test_a_naive_backdate_is_read_in_the_profile_timezone(session, profile, make_food):
    """ "Yesterday at noon" means noon where the user lives. Helsinki in August
    is UTC+3, so naive 12:00 must land at 09:00 UTC."""
    food = await make_food(name_en="soup", kcal=50, protein_g=3, carbs_g=5, fat_g=2)

    payload = await log(
        session, items=[{"food_id": food.id, "grams": 100}], ts="2026-08-03T12:00:00"
    )

    row = await session.get(MealLog, payload["log_id"])
    assert row.ts.astimezone(UTC) == datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
    assert payload["day_totals"]["local_date"] == "2026-08-03"


async def test_the_day_boundary_is_the_profile_timezone_midnight(session, profile, make_food):
    """A 00:30 snack belongs to the new day; 23:30 the evening before does not.
    In UTC those are 21:30 and 20:30 on the *same* UTC date — only the profile
    timezone separates them."""
    food = await make_food(name_en="snack", kcal=100, protein_g=1, carbs_g=1, fat_g=1)

    late = await log(session, items=[{"food_id": food.id, "grams": 100}], ts="2026-08-03T23:30")
    early = await log(session, items=[{"food_id": food.id, "grams": 100}], ts="2026-08-04T00:30")

    assert late["day_totals"]["local_date"] == "2026-08-03"
    assert early["day_totals"]["local_date"] == "2026-08-04"
    assert late["day_totals"]["kcal"] == pytest.approx(100.0)
    assert early["day_totals"]["kcal"] == pytest.approx(100.0)


async def test_planned_meals_count_toward_nothing_until_confirmed(session, profile, make_food):
    food = await make_food(name_en="planned dinner", kcal=200, protein_g=20, carbs_g=10, fat_g=8)

    payload = await log(session, items=[{"food_id": food.id, "grams": 100}], input_mode="plan")
    assert payload["planned"] is True
    assert payload["day_totals"]["kcal"] == pytest.approx(0.0)

    confirmed = await meals_domain.revise_log(
        session, subject=SUBJECT, log_id=payload["log_id"], changes={"planned": False}
    )
    assert confirmed["planned"] is False
    assert confirmed["day_totals"]["kcal"] == pytest.approx(200.0)


async def test_revising_grams_rescales_from_the_snapshot(session, profile, make_food):
    """The correction "that was 250 g, not 400" must use the macros that were
    true at log time, even if the food row has been edited since."""
    food = await make_food(name_en="rice", kcal=130, protein_g=3, carbs_g=28, fat_g=0.5)
    payload = await log(session, items=[{"food_id": food.id, "grams": 400}])

    row = await session.get(Food, food.id)
    row.kcal = 999
    await session.commit()

    revised = await meals_domain.revise_log(
        session,
        subject=SUBJECT,
        log_id=payload["log_id"],
        changes={"items": [{"food_id": food.id, "grams": 250}]},
    )

    (item,) = revised["items"]
    assert item["grams"] == 250.0
    assert item["kcal"] == pytest.approx(325.0)  # 130/100g, not 999


async def test_a_swapped_food_snapshots_todays_definition(session, profile, make_food):
    wrong = await make_food(name_en="cola", kcal=42, protein_g=0, carbs_g=10, fat_g=0)
    right = await make_food(name_en="cola zero", kcal=0.3, protein_g=0, carbs_g=0, fat_g=0)
    payload = await log(session, items=[{"food_id": wrong.id, "grams": 330}])

    revised = await meals_domain.revise_log(
        session,
        subject=SUBJECT,
        log_id=payload["log_id"],
        changes={"items": [{"food_id": right.id, "grams": 330}]},
    )

    (item,) = revised["items"]
    assert item["food_id"] == right.id
    assert item["kcal"] == pytest.approx(0.99)
    assert revised["day_totals"]["kcal"] == pytest.approx(0.99)


async def test_revising_ts_moves_the_log_between_days(session, profile, make_food):
    food = await make_food(name_en="lunch", kcal=500, protein_g=30, carbs_g=40, fat_g=20)
    payload = await log(session, items=[{"food_id": food.id, "grams": 100}])

    revised = await meals_domain.revise_log(
        session,
        subject=SUBJECT,
        log_id=payload["log_id"],
        changes={"ts": "2026-08-01T13:00"},
    )

    assert revised["day_totals"]["local_date"] == "2026-08-01"
    assert revised["day_totals"]["kcal"] == pytest.approx(500.0)


async def test_unknown_revision_fields_fail_loudly(session, profile, make_food):
    food = await make_food(name_en="x", kcal=1, protein_g=0, carbs_g=0, fat_g=0)
    payload = await log(session, items=[{"food_id": food.id, "grams": 100}])

    with pytest.raises(meals_domain.InvalidLog, match="calories"):
        await meals_domain.revise_log(
            session, subject=SUBJECT, log_id=payload["log_id"], changes={"calories": 100}
        )


# --- delete_log ----------------------------------------------------------------


async def test_deleting_a_log_removes_it_from_the_day(session, profile, make_food):
    food = await make_food(name_en="test entry", kcal=500, protein_g=20, carbs_g=50, fat_g=20)
    kept = await log(session, items=[{"food_id": food.id, "grams": 100}])
    doomed = await log(session, items=[{"food_id": food.id, "grams": 100}])

    payload = await meals_domain.delete_log(session, subject=SUBJECT, log_id=doomed["log_id"])

    assert payload["deleted_log_id"] == doomed["log_id"]
    assert payload["day_totals"]["kcal"] == pytest.approx(500.0)
    assert payload["day_totals"]["items_logged"] == 1

    with pytest.raises(meals_domain.LogNotFound):
        await meals_domain.revise_log(
            session, subject=SUBJECT, log_id=doomed["log_id"], changes={"notes": "gone"}
        )
    revisable = await meals_domain.revise_log(
        session, subject=SUBJECT, log_id=kept["log_id"], changes={"notes": "still here"}
    )
    assert revisable["notes"] == "still here"


async def test_another_users_log_cannot_be_deleted(session, profile, make_food):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    food = await make_food(name_en="oats", kcal=370, protein_g=13, carbs_g=60, fat_g=7)
    theirs = await meals_domain.log_meal(
        session, subject=OTHER_SUBJECT, items=[{"food_id": food.id, "grams": 100}]
    )

    with pytest.raises(meals_domain.LogNotFound):
        await meals_domain.delete_log(session, subject=SUBJECT, log_id=theirs["log_id"])


async def test_rest_deletes_a_log(api, profile, session, make_food):
    food = await make_food(name_en="rest bread", kcal=250, protein_g=8, carbs_g=45, fat_g=3)
    created = (
        await api.post("/api/logs/meals", json={"items": [{"food_id": food.id, "grams": 100}]})
    ).json()

    response = await api.delete(f"/api/logs/meals/{created['log_id']}")

    assert response.status_code == 200
    assert response.json()["day_totals"]["items_logged"] == 0
    assert (await api.delete(f"/api/logs/meals/{created['log_id']}")).status_code == 404


# --- scoping ------------------------------------------------------------------


async def test_another_users_private_food_cannot_be_logged(session, profile, make_food):
    private = await make_food(name_en="their secret shake", owner_id=OTHER_SUBJECT, kcal=100)

    with pytest.raises(meals_domain.UnknownFood):
        await log(session, items=[{"food_id": private.id, "grams": 100}])


async def test_another_users_log_cannot_be_revised(session, profile, make_food):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    food = await make_food(name_en="oats", kcal=370, protein_g=13, carbs_g=60, fat_g=7)
    theirs = await meals_domain.log_meal(
        session, subject=OTHER_SUBJECT, items=[{"food_id": food.id, "grams": 100}]
    )

    with pytest.raises(meals_domain.LogNotFound):
        await meals_domain.revise_log(
            session, subject=SUBJECT, log_id=theirs["log_id"], changes={"notes": "mine now"}
        )


async def test_day_totals_do_not_mix_subjects(session, profile, make_food):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    food = await make_food(name_en="shared bread", kcal=250, protein_g=8, carbs_g=45, fat_g=3)

    await meals_domain.log_meal(
        session, subject=OTHER_SUBJECT, items=[{"food_id": food.id, "grams": 1000}]
    )
    payload = await log(session, items=[{"food_id": food.id, "grams": 100}])

    assert payload["day_totals"]["kcal"] == pytest.approx(250.0)


# --- the two surfaces ----------------------------------------------------------


async def test_rest_and_mcp_operate_on_the_same_log(session, profile, make_food, mcp_client, api):
    """Log over MCP, correct over REST: one log, one shape. The parity rule is
    that both adapters are thin over the same domain function — a log created
    on one surface must be a first-class citizen on the other."""
    food = await make_food(name_en="parity bread", kcal=250, protein_g=8, carbs_g=45, fat_g=3)

    result = await mcp_client.call_tool(
        "log_meal", {"items": [{"food_id": food.id, "grams": 100}], "meal": "lunch"}
    )
    logged = result.structured_content

    response = await api.patch(
        f"/api/logs/meals/{logged['log_id']}", json={"changes": {"notes": "actually two slices"}}
    )
    assert response.status_code == 200
    revised = response.json()

    assert set(revised) == set(logged)
    assert revised["log_id"] == logged["log_id"]
    assert revised["items"] == logged["items"]
    assert revised["notes"] == "actually two slices"


async def test_rest_rejects_a_meal_with_no_items(api, profile):
    response = await api.post("/api/logs/meals", json={"items": []})
    assert response.status_code == 422


async def test_rest_404s_a_foreign_log(api, profile, session, make_food):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    food = await make_food(name_en="oats", kcal=370, protein_g=13, carbs_g=60, fat_g=7)
    theirs = await meals_domain.log_meal(
        session, subject=OTHER_SUBJECT, items=[{"food_id": food.id, "grams": 100}]
    )

    response = await api.patch(
        f"/api/logs/meals/{theirs['log_id']}", json={"changes": {"notes": "x"}}
    )
    assert response.status_code == 404


async def test_logging_without_a_profile_is_an_error(session, make_food):
    """No profile means registration never completed; there is no timezone to
    define the caller's day, so the log is refused rather than guessed at."""
    food = await make_food(name_en="orphan food", kcal=1, protein_g=0, carbs_g=0, fat_g=0)

    with pytest.raises(profile_domain.ProfileNotFound):
        await log(session, items=[{"food_id": food.id, "grams": 100}])
