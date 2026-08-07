"""Account deletion — the Annos half of the two-sided erasure.

What must not regress: the wipe is total (every table, including the ones
that only cascade), it touches nobody else's rows, a wrong nickname deletes
nothing at all, and the route is web-only by credential shape — an MCP
client's opaque token cannot reach it however the tools are chained.
"""

import pytest
from sqlalchemy import select

from annos.config import settings
from annos.domain import account as account_domain
from annos.domain import body as body_domain
from annos.domain import days as days_domain
from annos.domain import exercise as exercise_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.domain import templates as templates_domain
from annos.models import MealLogItem, MealTemplateItem, ServingUnit, StrengthSet
from conftest import OTHER_SUBJECT, SUBJECT


@pytest.fixture
async def full_account(session, make_food):
    """One of everything Annos can hold, for both subjects — deletion is only
    testable against a neighbour who must keep their rows."""
    profile = await profile_domain.create_profile(session, subject=SUBJECT)
    await profile_domain.update_profile(
        session, subject=SUBJECT, changes={"coaching_notes": "high protein"}
    )
    own_food = await make_food(
        name_en="own porridge", source="user", owner_id=SUBJECT, serving_units=(("DL", 60),)
    )
    await meals_domain.log_meal(
        session, subject=SUBJECT, items=[{"food_id": own_food.id, "grams": 150}]
    )
    await templates_domain.save_template(
        session, subject=SUBJECT, name="breakfast", items=[{"food_id": own_food.id, "grams": 150}]
    )
    await body_domain.log_weight(session, subject=SUBJECT, weight_kg=84.0)
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2200,
        kcal_rest=1800,
        protein_training=150,
        protein_rest=130,
    )
    await days_domain.set_day_type(session, subject=SUBJECT, day_type="training")
    await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="strength",
        sets=[{"exercise": "Bench Press", "reps": 5, "weight_kg": 100}],
    )

    other_profile = await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    other_food = await make_food(name_en="neighbour oats", source="user", owner_id=OTHER_SUBJECT)
    await meals_domain.log_meal(
        session, subject=OTHER_SUBJECT, items=[{"food_id": other_food.id, "grams": 100}]
    )
    await body_domain.log_weight(session, subject=OTHER_SUBJECT, weight_kg=70.0)

    return {"nickname": profile.nickname, "other_nickname": other_profile.nickname}


async def test_deletion_erases_everything_and_only_this_account(session, full_account):
    receipt = await account_domain.delete_account(
        session, subject=SUBJECT, nickname=full_account["nickname"]
    )

    assert receipt["deleted"] is True
    assert receipt["nickname"] == full_account["nickname"]
    # Every named table reports what it gave up.
    assert receipt["erased"]["user_profile"] == 1
    assert receipt["erased"]["meal_logs"] == 1
    assert receipt["erased"]["meal_templates"] == 1
    assert receipt["erased"]["exercise_logs"] == 1
    assert receipt["erased"]["exercises"] == 1
    assert receipt["erased"]["foods"] == 1
    assert receipt["erased"]["body_metrics"] == 1
    assert receipt["erased"]["goal_phases"] == 1
    assert receipt["erased"]["day_types"] == 1
    assert receipt["erased"]["coaching_note_revisions"] == 1

    assert await account_domain._remaining_rows(session, SUBJECT) == 0
    # The cascading children are gone too — the neighbour's one item is all
    # that survives in any child table.
    assert len((await session.execute(select(MealLogItem))).scalars().all()) == 1
    assert (await session.execute(select(MealTemplateItem))).scalars().all() == []
    assert (await session.execute(select(StrengthSet))).scalars().all() == []
    assert (await session.execute(select(ServingUnit))).scalars().all() == []

    # The neighbour keeps every row.
    assert await account_domain._remaining_rows(session, OTHER_SUBJECT) == 4
    remaining = await profile_domain.get_profile(session, subject=OTHER_SUBJECT)
    assert remaining.nickname == full_account["other_nickname"]


async def test_wrong_nickname_deletes_nothing(session, full_account):
    before = await account_domain._remaining_rows(session, SUBJECT)

    with pytest.raises(account_domain.NicknameMismatch):
        await account_domain.delete_account(session, subject=SUBJECT, nickname="not-the-nickname")

    assert await account_domain._remaining_rows(session, SUBJECT) == before


async def test_no_profile_is_not_found(session):
    with pytest.raises(profile_domain.ProfileNotFound):
        await account_domain.delete_account(session, subject=SUBJECT, nickname="anything")


async def test_route_deletes_with_matching_nickname(api, session, full_account):
    response = await api.request(
        "DELETE", "/api/account", json={"nickname": full_account["nickname"]}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted"] is True
    assert payload["erased"]["user_profile"] == 1
    assert await account_domain._remaining_rows(session, SUBJECT) == 0


async def test_route_refuses_a_mismatch(api, session, full_account):
    response = await api.request("DELETE", "/api/account", json={"nickname": "wrong-name"})

    assert response.status_code == 422
    assert await account_domain._remaining_rows(session, SUBJECT) > 0


async def test_route_refuses_mcp_shaped_credentials(api, monkeypatch, full_account):
    """An opaque OAuth token — the only credential an MCP client holds — is
    refused by shape before any validation. No chain of tool calls can end
    in account destruction."""
    monkeypatch.setattr(settings, "dev_subject", None)

    response = await api.request(
        "DELETE",
        "/api/account",
        json={"nickname": full_account["nickname"]},
        headers={"Authorization": "Bearer an-opaque-oauth-access-token"},
    )

    assert response.status_code == 403


async def test_route_without_credentials_is_unauthorized(api, monkeypatch):
    monkeypatch.setattr(settings, "dev_subject", None)

    response = await api.request("DELETE", "/api/account", json={"nickname": "x"})

    assert response.status_code == 401
