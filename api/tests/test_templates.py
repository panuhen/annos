"""Templates: a meal saved as one loggable unit, expanded at log time.

What must not regress: expansion happens server-side and the snapshot
discipline is untouched (a template logged after a food edit uses that day's
definition); names replace rather than duplicate; recipes scale by grams of
yield; and everything is scoped by subject.
"""

import pytest

from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.domain import templates as templates_domain
from conftest import OTHER_SUBJECT, SUBJECT


@pytest.fixture
async def profile(session):
    return await profile_domain.create_profile(session, subject=SUBJECT)


@pytest.fixture
async def breakfast(session, profile, make_food):
    """Two foods and a saved template over them."""
    bread = await make_food(name_fi="ruisleipä", kcal=218, protein_g=8.5, carbs_g=36, fat_g=1.5)
    cheese = await make_food(name_fi="juusto", kcal=350, protein_g=25, carbs_g=0, fat_g=27)
    saved = await templates_domain.save_template(
        session,
        subject=SUBJECT,
        name="usual breakfast",
        items=[
            {"food_id": bread.id, "grams": 60},
            {"food_id": cheese.id, "grams": 20},
        ],
    )
    return {"bread": bread, "cheese": cheese, "saved": saved}


# --- save_template -----------------------------------------------------------


async def test_saving_returns_the_template(breakfast):
    saved = breakfast["saved"]

    assert saved["created"] is True
    assert saved["name"] == "usual breakfast"
    assert [item["grams"] for item in saved["items"]] == [60.0, 20.0]


async def test_saving_the_same_name_replaces_the_contents(session, breakfast):
    saved = await templates_domain.save_template(
        session,
        subject=SUBJECT,
        name="usual breakfast",
        items=[{"food_id": breakfast["bread"].id, "grams": 90}],
    )

    assert saved["created"] is False
    assert saved["template_id"] == breakfast["saved"]["template_id"]
    assert [item["grams"] for item in saved["items"]] == [90.0]


async def test_a_template_needs_a_name_and_items(session, profile, make_food):
    food = await make_food(name_fi="kaurapuuro", kcal=60)

    with pytest.raises(templates_domain.InvalidTemplate, match="name"):
        await templates_domain.save_template(
            session, subject=SUBJECT, name="  ", items=[{"food_id": food.id, "grams": 100}]
        )
    with pytest.raises(templates_domain.InvalidTemplate, match="at least one"):
        await templates_domain.save_template(session, subject=SUBJECT, name="empty", items=[])


async def test_another_users_private_food_cannot_be_templated(session, profile, make_food):
    private = await make_food(name_fi="salainen", owner_id=OTHER_SUBJECT, kcal=100)

    with pytest.raises(templates_domain.InvalidTemplate, match="no such food"):
        await templates_domain.save_template(
            session, subject=SUBJECT, name="sneaky", items=[{"food_id": private.id, "grams": 50}]
        )


# --- list_templates ----------------------------------------------------------


async def test_listing_resolves_names_and_estimates_kcal(session, breakfast):
    listed = await templates_domain.list_templates(session, subject=SUBJECT)

    (template,) = listed["templates"]
    assert template["name"] == "usual breakfast"
    assert [item["name"] for item in template["items"]] == ["ruisleipä", "juusto"]
    # 218*0.6 + 350*0.2 = 130.8 + 70 = 200.8
    assert template["kcal"] == pytest.approx(200.8)


async def test_templates_are_scoped_by_subject(session, breakfast):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)

    listed = await templates_domain.list_templates(session, subject=OTHER_SUBJECT)

    assert listed["templates"] == []


# --- revise_template / delete_template ----------------------------------------


async def test_revising_renames_and_restates(session, breakfast):
    revised = await templates_domain.revise_template(
        session,
        subject=SUBJECT,
        template_id=breakfast["saved"]["template_id"],
        changes={
            "name": "weekend breakfast",
            "items": [{"food_id": breakfast["bread"].id, "grams": 90}],
        },
    )

    assert revised["name"] == "weekend breakfast"
    assert [item["grams"] for item in revised["items"]] == [90.0]


async def test_renaming_onto_an_existing_name_is_refused(session, breakfast):
    await templates_domain.save_template(
        session,
        subject=SUBJECT,
        name="other",
        items=[{"food_id": breakfast["bread"].id, "grams": 30}],
    )

    with pytest.raises(templates_domain.InvalidTemplate, match="already exists"):
        await templates_domain.revise_template(
            session,
            subject=SUBJECT,
            template_id=breakfast["saved"]["template_id"],
            changes={"name": "other"},
        )


async def test_the_yield_can_be_set_and_cleared(session, breakfast):
    template_id = breakfast["saved"]["template_id"]

    with_yield = await templates_domain.revise_template(
        session, subject=SUBJECT, template_id=template_id, changes={"total_grams": 500}
    )
    assert with_yield["total_grams"] == 500.0

    cleared = await templates_domain.revise_template(
        session, subject=SUBJECT, template_id=template_id, changes={"total_grams": None}
    )
    assert cleared["total_grams"] is None


async def test_deleting_a_template_leaves_logs_alone(session, breakfast):
    logged = await meals_domain.log_meal(
        session, subject=SUBJECT, items=[{"template_id": breakfast["saved"]["template_id"]}]
    )

    await templates_domain.delete_template(
        session, subject=SUBJECT, template_id=breakfast["saved"]["template_id"]
    )

    listed = await templates_domain.list_templates(session, subject=SUBJECT)
    assert listed["templates"] == []
    # The log carries its own snapshots; the template was never a dependency.
    revised = await meals_domain.revise_log(
        session, subject=SUBJECT, log_id=logged["log_id"], changes={"notes": "still fine"}
    )
    assert len(revised["items"]) == 2


async def test_another_users_template_cannot_be_revised_or_deleted(session, breakfast):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)

    with pytest.raises(templates_domain.TemplateNotFound):
        await templates_domain.revise_template(
            session,
            subject=OTHER_SUBJECT,
            template_id=breakfast["saved"]["template_id"],
            changes={"name": "mine now"},
        )
    with pytest.raises(templates_domain.TemplateNotFound):
        await templates_domain.delete_template(
            session, subject=OTHER_SUBJECT, template_id=breakfast["saved"]["template_id"]
        )


async def test_rest_revises_and_deletes_a_template(api, breakfast):
    template_id = breakfast["saved"]["template_id"]

    revised = await api.patch(
        f"/api/templates/{template_id}", json={"changes": {"name": "renamed"}}
    )
    assert revised.status_code == 200
    assert revised.json()["name"] == "renamed"

    deleted = await api.delete(f"/api/templates/{template_id}")
    assert deleted.status_code == 200
    assert (await api.delete(f"/api/templates/{template_id}")).status_code == 404


# --- logging a template ------------------------------------------------------


async def test_logging_a_template_expands_to_its_foods(session, breakfast):
    payload = await meals_domain.log_meal(
        session,
        subject=SUBJECT,
        items=[{"template_id": breakfast["saved"]["template_id"]}],
        meal="breakfast",
    )

    assert [item["food_id"] for item in payload["items"]] == [
        breakfast["bread"].id,
        breakfast["cheese"].id,
    ]
    assert payload["day_totals"]["kcal"] == pytest.approx(200.8)


async def test_portions_scale_the_template(session, breakfast):
    payload = await meals_domain.log_meal(
        session,
        subject=SUBJECT,
        items=[{"template_id": breakfast["saved"]["template_id"], "portions": 0.5}],
    )

    assert [float(item["grams"]) for item in payload["items"]] == [30.0, 10.0]


async def test_grams_scale_a_recipe_by_its_yield(session, profile, make_food):
    """A pot of soup weighing 2000 g; eating 500 g takes a quarter of it."""
    soup_base = await make_food(name_fi="liemi", kcal=30, protein_g=1, carbs_g=4, fat_g=1)
    saved = await templates_domain.save_template(
        session,
        subject=SUBJECT,
        name="soup",
        items=[{"food_id": soup_base.id, "grams": 1600}],
        total_grams=2000,
    )

    payload = await meals_domain.log_meal(
        session, subject=SUBJECT, items=[{"template_id": saved["template_id"], "grams": 500}]
    )

    (item,) = payload["items"]
    assert float(item["grams"]) == pytest.approx(400.0)  # 1600 * 500/2000


async def test_grams_without_a_yield_is_refused(session, breakfast):
    with pytest.raises(meals_domain.InvalidLog, match="total_grams"):
        await meals_domain.log_meal(
            session,
            subject=SUBJECT,
            items=[{"template_id": breakfast["saved"]["template_id"], "grams": 100}],
        )


async def test_templates_mix_with_plain_items(session, breakfast, make_food):
    apple = await make_food(name_fi="omena", kcal=52, protein_g=0.3, carbs_g=12, fat_g=0.2)

    payload = await meals_domain.log_meal(
        session,
        subject=SUBJECT,
        items=[
            {"template_id": breakfast["saved"]["template_id"]},
            {"food_id": apple.id, "grams": 150},
        ],
    )

    assert len(payload["items"]) == 3


async def test_the_snapshot_uses_log_day_definitions(session, breakfast):
    """A template is a shorthand, not a second source of truth: edit the food,
    log the template, and the log carries the edited values."""
    breakfast["bread"].kcal = 250
    await session.commit()

    payload = await meals_domain.log_meal(
        session, subject=SUBJECT, items=[{"template_id": breakfast["saved"]["template_id"]}]
    )

    bread_item = payload["items"][0]
    assert bread_item["kcal"] == pytest.approx(150.0)  # 250 * 0.6


async def test_another_users_template_cannot_be_logged(session, breakfast):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)

    with pytest.raises(templates_domain.TemplateNotFound):
        await meals_domain.log_meal(
            session,
            subject=OTHER_SUBJECT,
            items=[{"template_id": breakfast["saved"]["template_id"]}],
        )


# --- the two surfaces --------------------------------------------------------


async def test_rest_saves_lists_and_logs_a_template(api, breakfast):
    listed = (await api.get("/api/templates")).json()
    assert [t["name"] for t in listed["templates"]] == ["usual breakfast"]

    template_id = listed["templates"][0]["template_id"]
    response = await api.post(
        "/api/logs/meals", json={"items": [{"template_id": template_id, "portions": 2}]}
    )

    assert response.status_code == 201
    assert [float(item["grams"]) for item in response.json()["items"]] == [120.0, 40.0]


async def test_rest_saving_needs_items(api, profile):
    response = await api.post("/api/templates", json={"name": "empty", "items": []})

    assert response.status_code == 422
