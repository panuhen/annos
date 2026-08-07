"""Day-type marks: the user's say on what kind of day a date is.

What must not regress: a mark upserts on the day, wins over the default in
both directions, and days without a mark stay an honest labelled assumption
— the table never records a default as if the user had said it.
"""

from datetime import date

import pytest

from annos.domain import days as days_domain
from annos.domain import profile as profile_domain
from annos.models import DayTypeMark
from conftest import OTHER_SUBJECT, SUBJECT


@pytest.fixture
async def profile(session):
    return await profile_domain.create_profile(session, subject=SUBJECT)


async def test_a_mark_defaults_to_today_in_the_profile_timezone(session, profile):
    payload = await days_domain.set_day_type(session, subject=SUBJECT, day_type="training")

    assert payload["day_type"] == "training"
    assert payload["date"] == payload["server_time"]["local_date"]


async def test_marking_again_replaces_instead_of_duplicating(session, profile):
    await days_domain.set_day_type(session, subject=SUBJECT, day_type="training", date="2026-08-03")
    payload = await days_domain.set_day_type(
        session, subject=SUBJECT, day_type="rest", date="2026-08-03"
    )

    assert payload["day_type"] == "rest"
    marks = await session.scalars(
        DayTypeMark.__table__.select().where(DayTypeMark.subject == SUBJECT)
    )
    assert len(list(marks)) == 1


async def test_an_unknown_day_type_is_refused(session, profile):
    with pytest.raises(days_domain.InvalidDayType, match="day_type"):
        await days_domain.set_day_type(session, subject=SUBJECT, day_type="leg day")


async def test_a_malformed_date_is_refused(session, profile):
    with pytest.raises(days_domain.InvalidDayType, match="ISO 8601"):
        await days_domain.set_day_type(
            session, subject=SUBJECT, day_type="training", date="yesterday"
        )


async def test_marks_are_scoped_by_subject(session, profile):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    await days_domain.set_day_type(
        session, subject=OTHER_SUBJECT, day_type="training", date="2026-08-03"
    )

    day_type, source = await days_domain.resolve_day_type(
        session, subject=SUBJECT, on=date(2026, 8, 3), tz="Europe/Helsinki"
    )

    assert (day_type, source) == ("rest", "default")


# --- the two surfaces --------------------------------------------------------


async def test_rest_sets_a_day_type(api, profile):
    response = await api.put("/api/days/type", json={"day_type": "training", "date": "2026-08-03"})

    assert response.status_code == 200
    assert response.json()["day_type"] == "training"
    assert response.json()["date"] == "2026-08-03"


async def test_rest_refuses_an_unknown_day_type(api, profile):
    response = await api.put("/api/days/type", json={"day_type": "leg day"})

    assert response.status_code == 422


async def test_a_mark_set_over_mcp_is_visible_in_the_rest_summary(api, mcp_client, profile):
    result = await mcp_client.call_tool(
        "set_day_type", {"day_type": "training", "date": "2026-08-03"}
    )
    assert result.structured_content["day_type"] == "training"

    summary = (await api.get("/api/summary/daily", params={"date": "2026-08-03"})).json()

    assert summary["day_type"] == "training"
    assert summary["day_type_source"] == "manual"
