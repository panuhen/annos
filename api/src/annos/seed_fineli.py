"""Seed the food catalogue from Fineli's CSV package.

    uv run python -m annos.seed_fineli              # downloads the package
    uv run python -m annos.seed_fineli --zip PATH   # uses a local copy

Why the CSV and not the API: the whole database is 1.9 MB, which makes mirroring
obviously right — `find_food` becomes a local query with no dependency on THL's
uptime, and the API returns only a subset of the 74 components per food anyway.

Data © Finnish Institute for Health and Welfare, Fineli. CC-BY 4.0.

Three things about the files that are not obvious and will produce silent
nonsense if missed:

* **They are Latin-1**, despite `descript.txt` claiming ASCII. Read as UTF-8 and
  HEDELMÄSOKERI arrives mangled.
* **Every name is upper case.** Fineli's own API serves them cased — Finnish and
  Swedish in sentence case, English in title case — and the transforms below
  reproduce that exactly. `pg_trgm` lowercases, so this is presentation only.
* **Energy is kilojoules.** ENERC is kJ; kcal is derived.
"""

import argparse
import asyncio
import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from annos.db import SessionLocal
from annos.models import Food, NutrientComponent, ServingUnit, ServingUnitType

# Fineli basic package 2: 4 232 foods x 74 components. The download is behind an
# opaque numeric id on fineli.fi rather than a stable filename; if this 404s or
# returns something that isn't a zip, the open data page lists the current one.
PACKAGE_URL = "https://fineli.fi/fineli/content/file/49"
PACKAGE_PAGE = "https://fineli.fi/fineli/en/avoin-data"

ENCODING = "latin-1"
KJ_PER_KCAL = Decimal("4.184")

# Fineli component codes for the macros that get their own column. Everything
# else lands in `micros` keyed by the same codes.
ENERGY = "ENERC"
MACROS = {"protein_g": "PROT", "carbs_g": "CHOAVL", "fat_g": "FAT", "fiber_g": "FIBC"}

CHUNK = 1000

# Splits on whitespace, hyphens, slashes and brackets, but *not* apostrophes —
# 42 English names are possessive, and str.title() renders those "Farmer'S".
_WORD = re.compile(r"[^\s\-/()]+")


def sentence_case(name: str) -> str:
    """FINNISH AND SWEDISH -> Finnish and swedish, which is Fineli's own style."""
    return name[:1].upper() + name[1:].lower()


def title_case(name: str) -> str:
    return _WORD.sub(lambda m: m.group()[:1].upper() + m.group()[1:], name.lower())


def _decimal(raw: str | None) -> Decimal | None:
    """Fineli writes decimals the Finnish way: 1698,30."""
    if raw is None or not raw.strip():
        return None
    return Decimal(raw.strip().replace(",", "."))


@dataclass
class SeedReport:
    foods: int = 0
    serving_units: int = 0
    unit_types: int = 0
    components: int = 0
    skipped_no_values: list[int] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"foods              {self.foods}",
            f"serving units      {self.serving_units}",
            f"unit types         {self.unit_types}",
            f"nutrient components{self.components:>4}",
        ]
        if self.skipped_no_values:
            lines.append(
                f"skipped            {len(self.skipped_no_values)} food(s) with no component "
                f"values at all: {self.skipped_no_values}"
            )
        return "\n".join(lines)


class Package:
    """The CSV package, read straight out of the zip."""

    def __init__(self, archive: zipfile.ZipFile) -> None:
        self._zip = archive

    def rows(self, name: str) -> list[dict[str, str]]:
        with self._zip.open(f"{name}.csv") as raw:
            text = io.TextIOWrapper(raw, encoding=ENCODING, newline="")
            return list(csv.DictReader(text, delimiter=";"))

    def names(self, language: str) -> dict[str, str]:
        """FOODID -> name, cased the way Fineli's own API cases it."""
        case = title_case if language == "en" else sentence_case
        return {
            row["FOODID"]: case(row["FOODNAME"])
            for row in self.rows(f"foodname_{language.upper()}")
            if row["FOODNAME"].strip()
        }

    def thesaurus(self, stem: str) -> dict[str, dict[str, str]]:
        """code -> {fi, sv, en} from Fineli's parallel per-language files."""
        merged: dict[str, dict[str, str]] = {}
        for language in ("fi", "sv", "en"):
            for row in self.rows(f"{stem}_{language.upper()}"):
                merged.setdefault(row["THSCODE"], {})[language] = row["DESCRIPT"]
        return merged


def read_values(package: Package) -> dict[str, dict[str, Decimal]]:
    """FOODID -> {component code: value per 100 g}."""
    values: dict[str, dict[str, Decimal]] = {}
    for row in package.rows("component_value"):
        amount = _decimal(row["BESTLOC"])
        if amount is not None:
            values.setdefault(row["FOODID"], {})[row["EUFDNAME"]] = amount
    return values


def build_foods(package: Package) -> tuple[list[dict], list[int]]:
    names = {language: package.names(language) for language in ("fi", "sv", "en")}
    values = read_values(package)

    rows: list[dict] = []
    skipped: list[int] = []

    for food in package.rows("food"):
        fineli_id = food["FOODID"]
        components = values.get(fineli_id)

        # A handful of rows in food.csv have no measurements at all. Writing
        # them as 0 kcal would put a plausible-looking lie in the catalogue, so
        # they are left out and reported.
        if not components or ENERGY not in components:
            skipped.append(int(fineli_id))
            continue

        rows.append(
            {
                "fineli_id": int(fineli_id),
                "name_fi": names["fi"].get(fineli_id),
                "name_sv": names["sv"].get(fineli_id),
                "name_en": names["en"].get(fineli_id),
                "source": "fineli",
                "owner_id": None,
                "kcal": round(components[ENERGY] / KJ_PER_KCAL, 2),
                **{
                    column: components.get(code)
                    for column, code in MACROS.items()
                    if column != "fiber_g"
                },
                "fiber_g": components.get(MACROS["fiber_g"]),
                # Kept in Fineli's own codes and units; nutrient_components says
                # what each one means. ENERC stays in kJ here — kcal above is
                # the derived value, not a replacement.
                "micros": {code: float(value) for code, value in components.items()},
            }
        )

    # PROT/CHOAVL/FAT are present for every food that has any values at all, but
    # the columns are NOT NULL, so make the assumption explicit rather than
    # letting Postgres raise a less informative error.
    for row in rows:
        for column in ("protein_g", "carbs_g", "fat_g"):
            if row[column] is None:
                raise ValueError(f"food {row['fineli_id']} has energy but no {column}")

    return rows, skipped


async def _upsert(session: AsyncSession, table, rows: list[dict], *, key, update: list[str]) -> int:
    if not rows:
        return 0
    statement = pg_insert(table)
    statement = statement.on_conflict_do_update(
        index_elements=key, set_={column: statement.excluded[column] for column in update}
    )
    for start in range(0, len(rows), CHUNK):
        await session.execute(statement, rows[start : start + CHUNK])
    return len(rows)


async def seed(session: AsyncSession, package: Package) -> SeedReport:
    report = SeedReport()

    unit_names = package.thesaurus("foodunit")
    report.unit_types = await _upsert(
        session,
        ServingUnitType,
        [
            {"code": code, **{f"name_{lang}": text for lang, text in names.items()}}
            for code, names in unit_names.items()
        ],
        key=[ServingUnitType.code],
        update=["name_fi", "name_sv", "name_en"],
    )

    component_names = package.thesaurus("eufdname")
    report.components = await _upsert(
        session,
        NutrientComponent,
        [
            {
                "code": row["EUFDNAME"],
                "unit": row["COMPUNIT"],
                "class_code": row["CMPCLASS"],
                **{
                    f"name_{lang}": text
                    for lang, text in component_names.get(row["EUFDNAME"], {}).items()
                },
            }
            for row in package.rows("component")
        ],
        key=[NutrientComponent.code],
        update=["unit", "class_code", "name_fi", "name_sv", "name_en"],
    )

    food_rows, report.skipped_no_values = build_foods(package)
    report.foods = await _upsert(
        session,
        Food,
        food_rows,
        key=[Food.fineli_id],
        update=[
            "name_fi",
            "name_sv",
            "name_en",
            "kcal",
            "protein_g",
            "carbs_g",
            "fat_g",
            "fiber_g",
            "micros",
        ],
    )

    # Serving units hang off our surrogate id, not Fineli's, so the foods have
    # to be in the table before their units can reference them.
    await session.flush()
    report.serving_units = await _seed_serving_units(session, package)
    await session.commit()
    return report


async def _seed_serving_units(session: AsyncSession, package: Package) -> int:
    id_by_fineli = {
        fineli_id: food_id
        for food_id, fineli_id in (
            await session.execute(select(Food.id, Food.fineli_id).where(Food.fineli_id.isnot(None)))
        ).all()
    }

    rows = []
    for row in package.rows("foodaddunit"):
        food_id = id_by_fineli.get(int(row["FOODID"]))
        grams = _decimal(row["MASS"])
        if food_id is None or grams is None:
            continue
        rows.append({"food_id": food_id, "unit_code": row["FOODUNIT"], "grams": grams})

    return await _upsert(
        session,
        ServingUnit,
        rows,
        key=[ServingUnit.food_id, ServingUnit.unit_code],
        update=["grams"],
    )


def download(destination: Path) -> Path:
    with httpx.Client(follow_redirects=True, timeout=120.0) as client:
        response = client.get(PACKAGE_URL, headers={"User-Agent": "annos-seed"})
        response.raise_for_status()
    if not response.content.startswith(b"PK"):
        raise RuntimeError(
            f"{PACKAGE_URL} did not return a zip. The download ids are not stable — "
            f"check {PACKAGE_PAGE} for the current basic package 2 link."
        )
    destination.write_bytes(response.content)
    return destination


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, help="local copy of the Fineli CSV package")
    args = parser.parse_args()

    path = args.zip or download(Path("fineli-basic-2.zip"))

    with zipfile.ZipFile(path) as archive:
        package = Package(archive)
        async with SessionLocal() as session:
            report = await seed(session, package)

    print(report)


if __name__ == "__main__":
    asyncio.run(main())
