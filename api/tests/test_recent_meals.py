"""recent_meals: the memory a stateless client lacks.

What must not regress: the window is calendar days in the profile timezone
(today included), newest first, names in the reader's language, macros from
the log-time snapshot — and the window arithmetic, because an off-by-one here
silently loses "same as Tuesday" exactly one weekday per week.
"""

from datetime import date, timedelta

import pytest

from annos import servertime
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.domain import summary as summary_domain
from conftest import OTHER_SUBJECT, SUBJECT

TZ = "Europe/Helsinki"


@pytest.fixture
async def profile(session):
    return await profile_domain.create_profile(session, subject=SUBJECT)


def local_today() -> date:
    return date.fromisoformat(servertime.local_date(TZ))


async def log_on(session, food, day: date, clock: str = "12:00", **kwargs):
    return await meals_domain.log_meal(
        session,
        subject=SUBJECT,
        items=[{"food_id": food.id, "grams": 100}],
        ts=f"{day.isoformat()}T{clock}",
        **kwargs,
    )


async def test_the_window_is_calendar_days_today_included(session, profile, make_food):
    """days=7 means today and the six days before it — one of each weekday —
    counted in the profile timezone, not 168 hours back from now."""
    food = await make_food(name_en="oats", kcal=370)
    today = local_today()
    await log_on(session, food, today - timedelta(days=6), "00:00", meal="breakfast")
    await log_on(session, food, today - timedelta(days=7), "23:59", meal="dinner")

    recent = await summary_domain.recent_meals(session, subject=SUBJECT, days=7)

    (meal,) = recent["meals"]
    assert meal["meal"] == "breakfast"
    assert meal["date"] == (today - timedelta(days=6)).isoformat()
    assert recent["days"] == 7


async def test_newest_first_with_dates_and_relog_material(session, profile, make_food):
    food = await make_food(
        name_en="lunch bowl", kcal=550, protein_g=35, carbs_g=50, fat_g=20, fiber_g=6
    )
    today = local_today()
    await log_on(session, food, today - timedelta(days=2), "12:30", meal="lunch")
    await log_on(session, food, today, "08:00", meal="breakfast", notes="double portion")

    recent = await summary_domain.recent_meals(session, subject=SUBJECT)

    assert [m["meal"] for m in recent["meals"]] == ["breakfast", "lunch"]
    assert [m["date"] for m in recent["meals"]] == [
        today.isoformat(),
        (today - timedelta(days=2)).isoformat(),
    ]

    # Everything a client needs to act on a meal without a second call:
    # log_id for revise_log/delete_log, food_id + grams for log_meal.
    newest = recent["meals"][0]
    assert newest["log_id"]
    assert newest["notes"] == "double portion"
    assert newest["kcal"] == pytest.approx(550.0)
    (item,) = newest["items"]
    assert item["food_id"] == food.id
    assert item["name"] == "lunch bowl"
    assert item["grams"] == pytest.approx(100.0)
    assert item["protein_g"] == pytest.approx(35.0)
    assert item["fiber_g"] == pytest.approx(6.0)


async def test_the_date_is_the_profile_timezones_call(session, profile, make_food):
    """A 00:30 snack belongs to the new local day even though its UTC instant
    is still the old one — same day-boundary rule as everywhere."""
    food = await make_food(name_en="night snack", kcal=200)
    today = local_today()
    await log_on(session, food, today, "00:30")

    recent = await summary_domain.recent_meals(session, subject=SUBJECT, days=1)

    (meal,) = recent["meals"]
    assert meal["date"] == today.isoformat()
    # Helsinki is ahead of UTC year-round, so the UTC instant is yesterday's
    # evening — the date must come from the profile timezone, not from ts.
    assert meal["ts"] < f"{today.isoformat()}T00:30"


async def test_planned_meals_ride_along_flagged(session, profile, make_food):
    food = await make_food(name_en="planned dinner", kcal=600)
    await log_on(session, food, local_today(), "19:00", input_mode="plan")

    recent = await summary_domain.recent_meals(session, subject=SUBJECT)

    (meal,) = recent["meals"]
    assert meal["planned"] is True


async def test_names_resolve_in_the_readers_language(session, profile, make_food):
    food = await make_food(name_fi="Ruisleipä", name_sv="Rågbröd", name_en="Rye bread")
    await log_on(session, food, local_today())
    await profile_domain.update_profile(session, subject=SUBJECT, changes={"language": "sv"})

    recent = await summary_domain.recent_meals(session, subject=SUBJECT)

    assert recent["language"] == "sv"
    assert recent["meals"][0]["items"][0]["name"] == "Rågbröd"


async def test_another_accounts_meals_are_invisible(session, profile, make_food):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    food = await make_food(name_en="theirs", kcal=300)
    await meals_domain.log_meal(
        session, subject=OTHER_SUBJECT, items=[{"food_id": food.id, "grams": 100}]
    )

    recent = await summary_domain.recent_meals(session, subject=SUBJECT)

    assert recent["meals"] == []


@pytest.mark.parametrize("days", [0, -1, 32, "soon"])
async def test_days_outside_the_window_are_refused(session, profile, days):
    with pytest.raises(meals_domain.InvalidLog):
        await summary_domain.recent_meals(session, subject=SUBJECT, days=days)


async def test_rest_validates_days_at_the_boundary(api, profile):
    assert (await api.get("/api/logs/meals", params={"days": 0})).status_code == 422
    assert (await api.get("/api/logs/meals", params={"days": 32})).status_code == 422
    assert (await api.get("/api/logs/meals", params={"days": 31})).status_code == 200


async def test_the_two_surfaces_agree(api, mcp_client, session, profile, make_food):
    food = await make_food(name_en="parity oats", kcal=370, protein_g=13, carbs_g=60, fat_g=7)
    await log_on(session, food, local_today() - timedelta(days=1), "08:00", meal="breakfast")

    rest = (await api.get("/api/logs/meals")).json()
    mcp = (await mcp_client.call_tool("recent_meals")).structured_content

    # server_time differs by the clock between the two calls; everything else
    # must be byte-identical.
    rest.pop("server_time")
    mcp.pop("server_time")
    assert rest == mcp
    assert rest["meals"][0]["meal"] == "breakfast"
