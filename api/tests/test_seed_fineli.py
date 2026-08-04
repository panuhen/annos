"""The Fineli seed.

Driven by a synthetic package rather than the real 1.9 MB zip: the transforms
are what can break, and a fixture that runs in milliseconds gets run. The real
package is exercised by hand — see the Fineli note in re:call for the numbers a
full run produces.
"""

import io
import zipfile
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from annos import seed_fineli
from annos.models import Food, NutrientComponent, ServingUnit, ServingUnitType

# One food with everything, one with names but no measurements at all.
PACKAGE = {
    "food": [
        "FOODID;FOODNAME;FOODTYPE",
        "11049;BANAANI, KUORITTU;FOOD",
        "99999;TYHJÄ;FOOD",
    ],
    "foodname_FI": [
        "FOODID;FOODNAME;LANG",
        "11049;BANAANI, KUORITTU;FI",
        "99999;TYHJÄ;FI",
    ],
    "foodname_SV": ["FOODID;FOODNAME;LANG", "11049;BANAN, SKALAD;SV"],
    "foodname_EN": [
        "FOODID;FOODNAME;LANG",
        "11049;FARMER'S BANANA, WITHOUT SKIN;EN",
    ],
    "component_value": [
        "FOODID;EUFDNAME;BESTLOC;ACQTYPE",
        "11049;ENERC;366,42;S",
        "11049;PROT;1,20;S",
        "11049;CHOAVL;19,40;S",
        "11049;FAT;0,30;S",
        "11049;FIBC;1,70;S",
        "11049;FOL;21,0;S",
    ],
    "component": [
        "EUFDNAME;COMPUNIT;CMPCLASS;CMPCLASSP",
        "ENERC;KJ;ENERGY;MACROCMP",
        "FOL;UG;VITAMIN;VITAMIN",
    ],
    "eufdname_FI": ["THSCODE;DESCRIPT;LANG", "ENERC;energia, laskennallinen;FI", "FOL;folaatti;FI"],
    "eufdname_SV": ["THSCODE;DESCRIPT;LANG", "ENERC;energi;SV", "FOL;folat;SV"],
    "eufdname_EN": ["THSCODE;DESCRIPT;LANG", "ENERC;energy,calculated;EN", "FOL;folate;EN"],
    "foodunit_FI": ["THSCODE;DESCRIPT;LANG", "KPL_S;pieni (kpl);FI"],
    "foodunit_SV": ["THSCODE;DESCRIPT;LANG", "KPL_S;litet stycke;SV"],
    "foodunit_EN": ["THSCODE;DESCRIPT;LANG", "KPL_S;small piece;EN"],
    "foodaddunit": ["FOODID;FOODUNIT;MASS", "11049;KPL_S;100,00", "99999;KPL_S;50,00"],
}


@pytest.fixture
def package() -> seed_fineli.Package:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, lines in PACKAGE.items():
            # Latin-1, exactly as THL ships it. Reading these as UTF-8 is the
            # mistake this encodes against.
            archive.writestr(f"{name}.csv", "\r\n".join(lines).encode(seed_fineli.ENCODING))
    return seed_fineli.Package(zipfile.ZipFile(buffer))


# --- the casing transforms --------------------------------------------------


def test_finnish_becomes_sentence_case():
    """Fineli's own API serves "Banaani, kuorittu"; the CSV has it shouting."""
    assert seed_fineli.sentence_case("BANAANI, KUORITTU") == "Banaani, kuorittu"


def test_english_becomes_title_case():
    assert seed_fineli.title_case("BANANA, WITHOUT SKIN") == "Banana, Without Skin"


def test_possessives_survive_title_casing():
    """str.title() renders this "Farmer'S Cheese". 42 English names are
    possessive, so the naive version is visibly wrong."""
    assert seed_fineli.title_case("FARMER'S CHEESE SALAD") == "Farmer's Cheese Salad"


def test_hyphenated_words_are_capitalised_on_both_sides():
    assert seed_fineli.title_case("OIL-BASED DRESSING") == "Oil-Based Dressing"


# --- reading the package ----------------------------------------------------


def test_latin1_names_survive_the_round_trip(package):
    """The whole point of pinning the encoding: read as UTF-8 this is mojibake."""
    assert package.names("fi")["99999"] == "Tyhjä"


def test_energy_is_converted_from_kilojoules(package):
    rows, _ = seed_fineli.build_foods(package)

    # 366.42 kJ / 4.184 = 87.58 kcal, which is a banana. Decimal all the way
    # through, so this is exact rather than approximate.
    assert rows[0]["kcal"] == Decimal("87.58")


def test_a_food_with_no_measurements_is_skipped_not_zeroed(package):
    """0 kcal is a plausible-looking lie; absence is not."""
    rows, skipped = seed_fineli.build_foods(package)

    assert [row["fineli_id"] for row in rows] == [11049]
    assert skipped == [99999]


def test_micros_keep_fineli_codes_and_units(package):
    rows, _ = seed_fineli.build_foods(package)

    # ENERC stays in kJ here; the kcal column is derived, not a replacement.
    assert rows[0]["micros"]["ENERC"] == pytest.approx(366.42)
    assert rows[0]["micros"]["FOL"] == pytest.approx(21.0)


# --- writing it out ---------------------------------------------------------


async def test_seed_writes_foods_units_and_lookups(session, package):
    report = await seed_fineli.seed(session, package)

    assert (report.foods, report.unit_types, report.components) == (1, 1, 2)
    assert report.skipped_no_values == [99999]

    food = await session.scalar(select(Food))
    assert (food.name_fi, food.name_sv) == ("Banaani, kuorittu", "Banan, skalad")
    assert food.name_en == "Farmer's Banana, Without Skin"
    assert food.source == "fineli"
    assert food.owner_id is None


async def test_serving_units_are_attached_to_the_right_food(session, package):
    """Units reference our surrogate id, not Fineli's, and the skipped food's
    unit must not attach itself to whatever id happens to be free."""
    await seed_fineli.seed(session, package)

    units = (await session.execute(select(ServingUnit))).scalars().all()
    food = await session.scalar(select(Food))

    assert [(u.food_id, u.unit_code, float(u.grams)) for u in units] == [(food.id, "KPL_S", 100.0)]


async def test_lookups_carry_all_three_languages(session, package):
    await seed_fineli.seed(session, package)

    unit_type = await session.scalar(select(ServingUnitType))
    assert (unit_type.name_fi, unit_type.name_sv, unit_type.name_en) == (
        "pieni (kpl)",
        "litet stycke",
        "small piece",
    )

    folate = await session.get(NutrientComponent, "FOL")
    assert (folate.unit, folate.name_fi, folate.name_en) == ("UG", "folaatti", "folate")


async def test_seeding_twice_updates_rather_than_duplicates(session, package):
    """The seed re-runs whenever Fineli publishes a release, so it upserts.
    A second run that doubled the catalogue would be found much later."""
    await seed_fineli.seed(session, package)
    await seed_fineli.seed(session, package)

    assert await session.scalar(select(func.count()).select_from(Food)) == 1
    assert await session.scalar(select(func.count()).select_from(ServingUnit)) == 1
