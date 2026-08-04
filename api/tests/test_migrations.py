"""The migration is the schema — it is what production actually runs.

These use their own scratch database, because they tear the schema down and put
it back, which would pull the rug out from under every other test.
"""

import asyncio
import os
import subprocess
import sys

import asyncpg
import pytest

from conftest import API_DIR, URL, dsn

SCRATCH = f"{URL.database}_migrations"
SCRATCH_URL = URL.set(database=SCRATCH).render_as_string(hide_password=False)

TABLES = (
    "user_profile",
    "foods",
    "serving_units",
    "serving_unit_types",
    "nutrient_components",
)

TABLE_EXISTS = (
    "SELECT count(*) FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_name = ANY($1::text[])"
)
TYPE_EXISTS = "SELECT count(*) FROM pg_type WHERE typname = 'food_source'"


def alembic(*args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "ANNOS_DATABASE_URL": SCRATCH_URL,
            "ANNOS_MIGRATION_DATABASE_URL": SCRATCH_URL,
        },
    )
    if result.returncode != 0:
        raise AssertionError(f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result


async def _recreate() -> None:
    conn = await asyncpg.connect(dsn("postgres"))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{SCRATCH}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{SCRATCH}"')
    finally:
        await conn.close()


@pytest.fixture(scope="module", autouse=True)
def scratch_database() -> None:
    asyncio.run(_recreate())


async def state() -> tuple[int, int]:
    conn = await asyncpg.connect(dsn(SCRATCH))
    try:
        return (
            await conn.fetchval(TABLE_EXISTS, list(TABLES)),
            await conn.fetchval(TYPE_EXISTS),
        )
    finally:
        await conn.close()


async def test_upgrade_downgrade_round_trips():
    """Downgrade has to drop the enum type as well as the tables. A migration
    that leaves the type behind looks fine until the next upgrade, which then
    fails on a type that already exists."""
    alembic("upgrade", "head")
    assert await state() == (len(TABLES), 1)

    alembic("downgrade", "base")
    assert await state() == (0, 0)

    alembic("upgrade", "head")
    assert await state() == (len(TABLES), 1)


def test_the_enum_type_is_created_exactly_once():
    """A postgresql.ENUM left on its default create_type, *plus* an explicit
    .create(), emits CREATE TYPE twice and the migration dies on the second.
    This is the check from the tracker, automated."""
    sql = alembic("upgrade", "head", "--sql").stdout

    # One per enum: food_source (0001), meal_type and input_mode (0003).
    assert sql.count("CREATE TYPE") == 3


def test_autogenerate_neither_drops_better_auths_tables_nor_finds_drift():
    """Two things at once, because one command proves both.

    Better Auth owns tables in this same database under its default names. They
    are absent from Base.metadata, so without the include_object allowlist in
    alembic/env.py autogenerate compares them against nothing and cheerfully
    emits op.drop_table('user'). And with the models in sync, the diff should
    otherwise be empty — that is what catches a model edited without a
    migration.
    """
    alembic("upgrade", "head")

    async def plant_better_auth_table() -> None:
        conn = await asyncpg.connect(dsn(SCRATCH))
        try:
            await conn.execute('CREATE TABLE IF NOT EXISTS "user" (id text PRIMARY KEY)')
            await conn.execute('CREATE TABLE IF NOT EXISTS "session" (id text PRIMARY KEY)')
        finally:
            await conn.close()

    asyncio.run(plant_better_auth_table())

    generated = API_DIR / "alembic" / "versions" / "aaaaaaaaaaaa_autogenerate_check.py"
    try:
        alembic(
            "revision", "--autogenerate", "--rev-id", "aaaaaaaaaaaa", "-m", "autogenerate check"
        )
        body = generated.read_text()
    finally:
        generated.unlink(missing_ok=True)

    assert "drop_table" not in body
    assert "op." not in body, f"models have drifted from the migration:\n{body}"
