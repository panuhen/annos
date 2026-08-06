"""Trigram search, the three languages, and the scoping that keeps one user's
foods out of another's.

The inflection and umlaut cases are the reason `pg_trgm` was chosen over plain
`ILIKE` in the first place, so they are pinned here rather than left to a manual
curl. They cannot run on SQLite at all.
"""

import pytest

from annos.domain import foods as foods_domain
from annos.domain import profile as profile_domain
from conftest import OTHER_SUBJECT, SUBJECT


async def test_matches_finnish_inflection(session, make_food):
    """ "rahka" finds "Maitorahka" — Finnish compounds bury the searched word in
    the middle, which prefix matching would miss entirely."""
    await make_food(name_fi="Maitorahka", name_en="Quark")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="rahka")

    assert [hit.names["fi"] for hit in hits] == ["Maitorahka"]


async def test_matches_without_umlauts(session, make_food):
    """Typing "ruisleipa" on a keyboard without ä still finds Ruisleipä."""
    await make_food(name_fi="Ruisleipä")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="ruisleipa")

    assert [hit.names["fi"] for hit in hits] == ["Ruisleipä"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [("ruisleipä", "fi"), ("rågbröd", "sv"), ("rye bread", "en")],
)
async def test_all_three_languages_are_searched(session, make_food, query, expected):
    """One food, three names, and a query in any of them finds it. The user's
    own language is irrelevant to *matching* — only to what comes back."""
    await make_food(name_fi="Ruisleipä", name_sv="Rågbröd", name_en="Rye bread")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query=query)

    assert len(hits) == 1
    assert hits[0].names[expected].lower() == query


async def test_a_finnish_reader_can_search_in_english(session, make_food):
    """The point of searching every language regardless of preference: people
    switch mid-sentence, and Fineli's English names are sometimes the ones a
    label uses."""
    await profile_domain.create_profile(session, subject=SUBJECT)
    await profile_domain.update_profile(session, subject=SUBJECT, changes={"language": "fi"})
    await make_food(name_fi="Banaani, kuorittu", name_en="Banana, Without Skin")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="banana")

    assert len(hits) == 1


async def test_a_word_fragment_finds_the_compounds(session, make_food):
    """ "melon" finds every melon: the substring arm qualifies what whole-string
    similarity scores too low against Fineli's long compound names."""
    await make_food(name_fi="Vesimeloni, kuorittu", name_en="Watermelon, Without Skin")
    await make_food(name_fi="Hunajameloni, kuorittu", name_en="Honeydew Melon, Without Skin")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="melon")

    assert len(hits) == 2


async def test_the_finished_word_outranks_the_compounds_it_starts(session, make_food):
    """Mid-typing order: "hunaja" lists Hunaja first, Hunajameloni after —
    word similarity, not whole-string, decides the ranking."""
    await make_food(name_fi="Hunajameloni, kuorittu")
    await make_food(name_fi="Hunaja")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="hunaja")

    assert [hit.names["fi"] for hit in hits] == ["Hunaja", "Hunajameloni, kuorittu"]


async def test_empty_query_returns_nothing(session, make_food):
    """A blank query must not become "everything" — it short-circuits before
    the database sees it."""
    await make_food(name_fi="Maitorahka")

    assert await foods_domain.find_food(session, subject=SUBJECT, query="") == []
    assert await foods_domain.find_food(session, subject=SUBJECT, query="   ") == []


async def test_another_users_food_is_invisible(session, make_food):
    """The scoping rule that matters: a food someone else created from a label
    photo must never surface here."""
    await make_food(name_fi="Kaurapuuro", owner_id=OTHER_SUBJECT, source="label")

    assert await foods_domain.find_food(session, subject=SUBJECT, query="kaurapuuro") == []


async def test_own_food_is_visible_and_flagged_owned(session, make_food):
    await make_food(name_fi="Kaurapuuro", owner_id=SUBJECT, source="label")

    (hit,) = await foods_domain.find_food(session, subject=SUBJECT, query="kaurapuuro")

    assert hit.owned is True


async def test_global_food_is_not_flagged_owned(session, make_food):
    await make_food(name_fi="Kaurapuuro", source="fineli")

    (hit,) = await foods_domain.find_food(session, subject=SUBJECT, query="kaurapuuro")

    assert hit.owned is False


async def test_ranks_the_closer_match_first(session, make_food):
    await make_food(name_fi="Maitorahka maustamaton vähälaktoosinen")
    await make_food(name_fi="Rahka")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="rahka")

    assert hits[0].names["fi"] == "Rahka"


async def test_limit_caps_the_result_set(session, make_food):
    for n in range(5):
        await make_food(name_fi=f"Rahka {n}")

    hits = await foods_domain.find_food(session, subject=SUBJECT, query="rahka", limit=2)

    assert len(hits) == 2


# --- what goes over the wire ------------------------------------------------


async def test_payload_carries_macros_and_serving_units(session, make_food, make_unit_type):
    await make_unit_type("SLICE", name_fi="viipale", name_sv="skiva", name_en="slice")
    await make_food(
        name_fi="Ruisleipä",
        name_en="Rye bread",
        kcal=218,
        protein_g=8.5,
        carbs_g=36,
        fat_g=1.5,
        fiber_g=8.6,
        serving_units=(("SLICE", 30),),
    )

    (hit,) = await foods_domain.find_food(session, subject=SUBJECT, query="ruisleipä")
    payload = foods_domain.candidate_payload(hit, "fi")

    # Floats, not Decimal-as-string: the shape both adapters must agree on.
    assert payload["per_100g"] == {
        "kcal": 218.0,
        "protein_g": 8.5,
        "carbs_g": 36.0,
        "fat_g": 1.5,
        "fiber_g": 8.6,
    }
    assert payload["serving_units"] == [{"code": "SLICE", "name": "viipale", "grams": 30.0}]


@pytest.mark.parametrize(
    ("language", "expected"),
    [("fi", "Ruisleipä"), ("sv", "Rågbröd"), ("en", "Rye bread")],
)
async def test_payload_is_rendered_in_the_readers_language(session, make_food, language, expected):
    await make_food(name_fi="Ruisleipä", name_sv="Rågbröd", name_en="Rye bread")

    (hit,) = await foods_domain.find_food(session, subject=SUBJECT, query="ruisleipä")
    payload = foods_domain.candidate_payload(hit, language)

    assert payload["name"] == expected
    assert payload["name_language"] == language


async def test_a_missing_name_falls_back_and_says_so(session, make_food):
    """A label photo produces one language. An English reader gets the Finnish
    name rather than a blank, and `name_language` explains why it looks odd."""
    await make_food(name_fi="Kaurapuuro", owner_id=SUBJECT, source="label")

    (hit,) = await foods_domain.find_food(session, subject=SUBJECT, query="kaurapuuro")
    payload = foods_domain.candidate_payload(hit, "en")

    assert payload["name"] == "Kaurapuuro"
    assert payload["name_language"] == "fi"


async def test_an_unknown_unit_code_renders_as_itself(session, make_food):
    """Units from a label photo need not exist in Fineli's thesaurus. The code
    is a worse label than a word, but better than null."""
    await make_food(name_fi="Kaurapuuro", owner_id=SUBJECT, serving_units=(("SCOOP", 45),))

    (hit,) = await foods_domain.find_food(session, subject=SUBJECT, query="kaurapuuro")
    payload = foods_domain.candidate_payload(hit, "fi")

    assert payload["serving_units"] == [{"code": "SCOOP", "name": "SCOOP", "grams": 45.0}]


# --- which language a reader gets -------------------------------------------


async def test_reading_language_defaults_before_registration(session):
    """Search works without a profile, so the language lookup has to tolerate
    one being absent."""
    assert await foods_domain.reading_language(session, subject=SUBJECT) == "fi"


async def test_reading_language_follows_the_profile(session):
    await profile_domain.create_profile(session, subject=SUBJECT)
    await profile_domain.update_profile(session, subject=SUBJECT, changes={"language": "sv"})

    assert await foods_domain.reading_language(session, subject=SUBJECT) == "sv"
