"""Seed the MET activity catalog from the vendored Compendium CSV.

    uv run python -m annos.seed_activities

The CSV (`api/data/activities.csv`, 1 111 rows) was parsed from the official
2024 Adult Compendium of Physical Activities PDF and lives in the repo: the
dataset is small, static between Compendium editions, and vendoring removes
any runtime dependency on the publisher's site. English-only by decision —
see the Schema — exercise note.

Cite: Herrmann et al., 2024 Adult Compendium of Physical Activities
(https://pacompendium.com).

Upserts on the Compendium `code`, so re-running after a data fix updates in
place instead of duplicating.
"""

import asyncio
import csv
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert

from annos.db import SessionLocal
from annos.models import Activity

CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "activities.csv"

CHUNK = 500


def read_rows(path: Path = CSV_PATH) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            {
                "code": row["code"],
                "category": row["category"],
                "met": row["met"],
                "name": row["description"],
            }
            for row in csv.DictReader(f)
        ]


async def seed(path: Path = CSV_PATH) -> int:
    rows = read_rows(path)
    async with SessionLocal() as session:
        for start in range(0, len(rows), CHUNK):
            chunk = rows[start : start + CHUNK]
            stmt = pg_insert(Activity).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "name": stmt.excluded.name,
                    "category": stmt.excluded.category,
                    "met": stmt.excluded.met,
                },
            )
            await session.execute(stmt)
        await session.commit()
    return len(rows)


def main() -> None:
    count = asyncio.run(seed())
    print(f"seeded {count} activities from {CSV_PATH}")


if __name__ == "__main__":
    main()
