"""Export — everything the caller owns, and nothing anyone else does.

What must not regress: the dataset mirrors the deletion wipe table for table
(the two receipts must be comparable number for number), a neighbour's rows
never leak in, names resolve like every other read view, and the zip is a
faithful rendering of the same dataset the MCP tool returns.
"""

import io
import json
import zipfile

import pytest

from annos.domain import account as account_domain
from annos.domain import body as body_domain
from annos.domain import days as days_domain
from annos.domain import exercise as exercise_domain
from annos.domain import export as export_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.domain import templates as templates_domain
from conftest import OTHER_SUBJECT, SUBJECT


@pytest.fixture
async def full_account(session, make_food):
    """One of everything Annos can hold, plus a neighbour whose rows must
    never appear in the export."""
    profile = await profile_domain.create_profile(session, subject=SUBJECT)
    await profile_domain.update_profile(
        session, subject=SUBJECT, changes={"coaching_notes": "high protein"}
    )
    porridge = await make_food(
        name_fi="kaurapuuro",
        name_en="oat porridge",
        source="user",
        owner_id=SUBJECT,
        kcal=60,
        protein_g=2,
        fiber_g=1.5,
        serving_units=(("DL", 101),),
    )
    berries = await make_food(name_en="berries", source="user", owner_id=SUBJECT, kcal=50)
    await meals_domain.log_meal(
        session,
        subject=SUBJECT,
        items=[{"food_id": porridge.id, "grams": 250}, {"food_id": berries.id, "grams": 100}],
        notes="breakfast bowl",
    )
    await templates_domain.save_template(
        session,
        subject=SUBJECT,
        name="breakfast",
        items=[{"food_id": porridge.id, "grams": 250}, {"food_id": berries.id, "grams": 100}],
    )
    await body_domain.log_weight(session, subject=SUBJECT, weight_kg=84.0, waist_cm=90.0)
    await body_domain.set_goal_phase(
        session,
        subject=SUBJECT,
        kind="deficit",
        kcal_training=2200,
        kcal_rest=1800,
        protein_training=150,
        protein_rest=130,
        rate_target=-0.4,
    )
    await days_domain.set_day_type(session, subject=SUBJECT, day_type="training")
    await exercise_domain.log_exercise(
        session,
        subject=SUBJECT,
        kind="strength",
        sets=[
            {"exercise": "Bench Press", "reps": 5, "weight_kg": 100},
            {"exercise": "Bench Press", "reps": 5, "weight_kg": 100, "rpe": 8},
        ],
    )

    await profile_domain.create_profile(session, subject=OTHER_SUBJECT)
    neighbour_food = await make_food(
        name_en="neighbour oats", source="user", owner_id=OTHER_SUBJECT
    )
    await meals_domain.log_meal(
        session, subject=OTHER_SUBJECT, items=[{"food_id": neighbour_food.id, "grams": 100}]
    )
    await body_domain.log_weight(session, subject=OTHER_SUBJECT, weight_kg=70.0)

    return {"nickname": profile.nickname}


async def test_export_receipt_matches_deletion_receipt(session, full_account):
    """The flagship invariant: export-then-delete hands back two receipts
    whose keys and numbers match — the export covered exactly what the wipe
    erased, no table forgotten on either side."""
    dataset = await export_domain.export_account(session, subject=SUBJECT)
    receipt = await account_domain.delete_account(
        session, subject=SUBJECT, nickname=full_account["nickname"]
    )

    assert dataset["counts"] == receipt["erased"]


async def test_dataset_carries_the_data_and_only_this_accounts(session, full_account):
    dataset = await export_domain.export_account(session, subject=SUBJECT)

    assert dataset["export_format"] == export_domain.EXPORT_FORMAT
    assert dataset["nickname"] == full_account["nickname"]
    assert dataset["profile"]["coaching_notes"] == "high protein"
    assert dataset["coaching_history"][0]["notes"] == "high protein"

    # The meal: names resolve in the profile language with fallback, macros are
    # portion values, the raw per-100g snapshot rides along untouched.
    (meal,) = dataset["meals"]
    assert meal["notes"] == "breakfast bowl"
    assert meal["ts_utc"] and meal["date_local"]
    first, second = meal["items"]
    assert (first["food_name"], first["food_name_language"]) == ("kaurapuuro", "fi")
    assert (second["food_name"], second["food_name_language"]) == ("berries", "en")
    assert first["kcal"] == 150.0  # 60 kcal/100g × 250 g
    assert first["fiber_g"] == 3.75
    assert first["per_100g"]["kcal"] == 60.0
    assert first["food_source"] == "user"
    assert first["portion_estimated"] is False  # measured/guessed, beside the source

    # The session with its sets, named as the user logs them.
    (workout,) = dataset["exercise_sessions"]
    assert workout["kind"] == "strength"
    assert [s["set_no"] for s in workout["sets"]] == [1, 2]
    assert workout["sets"][0]["exercise"] == "Bench Press"
    assert workout["sets"][1]["rpe"] == 8.0

    (weight,) = dataset["weights"]
    assert (weight["weight_kg"], weight["waist_cm"]) == (84.0, 90.0)
    (phase,) = dataset["goal_phases"]
    assert (phase["kind"], phase["rate_target_kg_per_week"]) == ("deficit", -0.4)
    (mark,) = dataset["day_types"]
    assert mark["day_type"] == "training"

    (template,) = dataset["templates"]
    assert template["name"] == "breakfast"
    assert [i["food_name"] for i in template["items"]] == ["kaurapuuro", "berries"]

    # Own foods with all three name columns and their units; the neighbour's
    # food is nobody's business here.
    assert [f["name_fi"] or f["name_en"] for f in dataset["own_foods"]] == [
        "kaurapuuro",
        "berries",
    ]
    assert dataset["own_foods"][0]["serving_units"] == [{"unit_code": "DL", "grams": 101.0}]
    assert dataset["exercises"] == [
        {
            "exercise_id": dataset["exercises"][0]["exercise_id"],
            "name": "Bench Press",
            "muscle_group": None,
        }
    ]

    # JSON-safe all the way down: no Decimal or datetime survives.
    json.dumps(dataset)


async def test_csvs_flatten_one_row_per_item(session, full_account):
    dataset = await export_domain.export_account(session, subject=SUBJECT)
    files = export_domain.render_csvs(dataset)

    meals = files["meals.csv"].splitlines()
    assert meals[0].startswith("log_id,ts_utc,date_local,meal,planned,input_mode,notes,food_id")
    assert len(meals) == 3  # header + two items of the one meal
    assert "kaurapuuro" in meals[1] and "berries" in meals[2]

    sets = files["strength_sets.csv"].splitlines()
    assert len(sets) == 3
    assert "Bench Press" in sets[1]

    # Booleans print as machine words, not Python's True/False.
    assert ",false," in meals[1]
    assert files["day_types.csv"].splitlines()[1].endswith("training")
    assert set(files) == {
        "meals.csv",
        "exercise_sessions.csv",
        "strength_sets.csv",
        "weights.csv",
        "goal_phases.csv",
        "day_types.csv",
        "templates.csv",
        "own_foods.csv",
        "exercises.csv",
        "coaching_history.csv",
    }


async def test_zip_is_a_faithful_rendering(session, full_account):
    dataset = await export_domain.export_account(session, subject=SUBJECT)
    content, filename = export_domain.build_zip(dataset)

    assert filename == f"annos-export-{dataset['server_time']['local_date']}.zip"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names and "data.json" in names
        assert {n for n in names if n.startswith("csv/")} == {
            f"csv/{f}" for f in export_domain.render_csvs(dataset)
        }

        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["counts"] == dataset["counts"]
        assert manifest["nickname"] == dataset["nickname"]

        # data.json round-trips the dataset losslessly.
        assert json.loads(archive.read("data.json")) == json.loads(json.dumps(dataset))

        # Every CSV wears the BOM so Excel reads the umlauts.
        for name in names:
            if name.startswith("csv/"):
                assert archive.read(name).startswith(b"\xef\xbb\xbf")


async def test_route_serves_the_zip(api, session, full_account):
    response = await api.get("/api/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith('attachment; filename="annos-export-')
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["nickname"] == full_account["nickname"]
        assert manifest["counts"]["meal_logs"] == 1


async def test_route_without_a_profile_is_not_found(api):
    response = await api.get("/api/export")

    assert response.status_code == 404


async def test_tool_returns_the_same_dataset(mcp_client, session, full_account):
    result = await mcp_client.call_tool("export_my_data", {})
    dataset = result.data

    expected = await export_domain.export_account(session, subject=SUBJECT)
    # server_time moves between the two calls; everything else is identical.
    dataset.pop("server_time")
    expected.pop("server_time")
    assert json.loads(json.dumps(dataset)) == json.loads(json.dumps(expected))
