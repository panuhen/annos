"""Trigram search, and the scoping that keeps one user's foods out of another's.

The inflection and umlaut cases are the reason `pg_trgm` was chosen over plain
`ILIKE` in the first place, so they are pinned here rather than left to a manual
curl. They cannot run on SQLite at all.
"""

from annos.domain import foods as foods_domain
from conftest import OTHER_SUBJECT, SUBJECT


async def test_matches_finnish_inflection(session, make_food):
    """ "rahka" finds "Maitorahka" — Finnish compounds bury the searched word in
    the middle, which prefix matching would miss entirely."""
    await make_food("Maitorahka", name_fi="Maitorahka")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="rahka")

    assert [hit.name for hit in hits] == ["Maitorahka"]


async def test_matches_without_umlauts(session, make_food):
    """Typing "ruisleipa" on a keyboard without ä still finds Ruisleipä."""
    await make_food("Ruisleipä", name_fi="Ruisleipä")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="ruisleipa")

    assert [hit.name for hit in hits] == ["Ruisleipä"]


async def test_matches_on_the_finnish_name_too(session, make_food):
    """Both name columns are searched, so an English catalogue name is still
    reachable by what the user actually calls it."""
    await make_food("Rye bread", name_fi="Ruisleipä")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="ruisleipä")

    assert [hit.name for hit in hits] == ["Rye bread"]


async def test_empty_query_returns_nothing(session, make_food):
    """A blank query must not become "everything" — it short-circuits before
    the database sees it."""
    await make_food("Maitorahka")

    assert await foods_domain.find_food(session, subject=SUBJECT, query="") == []
    assert await foods_domain.find_food(session, subject=SUBJECT, query="   ") == []


async def test_another_users_food_is_invisible(session, make_food):
    """The scoping rule that matters: a food someone else created from a label
    photo must never surface here."""
    await make_food("Kaurapuuro", owner_id=OTHER_SUBJECT, source="label")

    assert await foods_domain.find_food(session, subject=SUBJECT, query="kaurapuuro") == []


async def test_own_food_is_visible_and_flagged_owned(session, make_food):
    await make_food("Kaurapuuro", owner_id=SUBJECT, source="label")

    (hit,) = await foods_domain.find_food(session, subject=SUBJECT, query="kaurapuuro")

    assert hit.owned is True


async def test_global_food_is_not_flagged_owned(session, make_food):
    await make_food("Kaurapuuro", source="fineli")

    (hit,) = await foods_domain.find_food(session, subject=SUBJECT, query="kaurapuuro")

    assert hit.owned is False


async def test_ranks_the_closer_match_first(session, make_food):
    await make_food("Maitorahka maustamaton vähälaktoosinen")
    await make_food("Rahka")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="rahka")

    assert [hit.name for hit in hits][0] == "Rahka"


async def test_limit_caps_the_result_set(session, make_food):
    for n in range(5):
        await make_food(f"Rahka {n}")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="rahka", limit=2)

    assert len(hits) == 2


async def test_candidate_carries_macros_and_serving_units(session, make_food):
    await make_food(
        "Ruisleipä",
        kcal=218,
        protein_g=8.5,
        carbs_g=36,
        fat_g=1.5,
        fiber_g=8.6,
        serving_units=(("slice", 30),),
    )

    (hit,) = await foods_domain.find_food(session, subject=SUBJECT, query="ruisleipä")
    payload = foods_domain.candidate_payload(hit)

    # Floats, not Decimal-as-string: the shape both adapters must agree on.
    assert payload["per_100g"] == {
        "kcal": 218.0,
        "protein_g": 8.5,
        "carbs_g": 36.0,
        "fat_g": 1.5,
        "fiber_g": 8.6,
    }
    assert payload["serving_units"] == [{"name": "slice", "grams": 30.0}]
