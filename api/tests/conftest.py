"""Shared fixtures.

**Real Postgres, never SQLite.** The schema leans on `pg_trgm` similarity, a
native enum, `jsonb` and `ON CONFLICT`; none of them have SQLite equivalents, so
a SQLite suite would run green while production broke.

The suite owns a separate database on the same server, dropped and rebuilt from
Alembic at the start of every run. Two things fall out of that for free: the
migrations are exercised on every run rather than trusted, and `db/grants.sql`
is applied against the migrated schema — so a migration that adds a table
without updating that file fails here instead of in production.
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]

# The two subjects every test shares. Two, because scoping — one user's private
# food never surfacing in another's search — is only testable with a second one.
SUBJECT = "test-subject-a"
OTHER_SUBJECT = "test-subject-b"

# Set before anything under `annos` is imported: db.py builds the engine at
# import time, and config.py reads the environment at import time too.
#
# Tests connect as the owner role, not annos_api: they truncate between tests
# and create Better Auth's table stand-in. test_schema.py opens its own
# annos_api connection for the quarantine check.
os.environ.setdefault(
    "ANNOS_DATABASE_URL", "postgresql+asyncpg://annos:annos@localhost:5433/annos_test"
)
os.environ.setdefault("ANNOS_MIGRATION_DATABASE_URL", os.environ["ANNOS_DATABASE_URL"])
os.environ.setdefault("ANNOS_DEV_SUBJECT", SUBJECT)

import asyncpg  # noqa: E402
from fastmcp import Client  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from annos.config import settings  # noqa: E402
from annos.db import Base, SessionLocal, engine  # noqa: E402
from annos.models import Food, ServingUnit  # noqa: E402  — also registers the metadata

URL = make_url(settings.database_url)

if not (URL.database or "").endswith("_test"):
    raise RuntimeError(
        f"refusing to run against database {URL.database!r}: the suite drops it and truncates "
        "every table in it. Point ANNOS_DATABASE_URL at a database whose name ends in _test."
    )

GRANTS_SQL = next(
    (
        path
        for path in (API_DIR.parent / "db" / "grants.sql", API_DIR / "db" / "grants.sql")
        if path.exists()
    ),
    None,
)


def dsn(database: str, *, username: str | None = None, password: str | None = None) -> str:
    """A libpq DSN for asyncpg, which doesn't understand SQLAlchemy's `+asyncpg`."""
    url = URL.set(drivername="postgresql", database=database)
    if username is not None:
        url = url.set(username=username, password=password or "")
    return url.render_as_string(hide_password=False)


async def _recreate_database() -> None:
    conn = await asyncpg.connect(dsn("postgres"))
    try:
        # FORCE: a previous run's leaked connection would otherwise block the drop.
        await conn.execute(f'DROP DATABASE IF EXISTS "{URL.database}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{URL.database}"')
    finally:
        await conn.close()


def _migrate() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")


async def _apply_grants() -> None:
    conn = await asyncpg.connect(dsn(URL.database))
    try:
        await conn.execute(GRANTS_SQL.read_text())
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    """Build the test database once per run. Deliberately synchronous: it must
    not share an event loop with the tests, whose loops are per-test."""
    asyncio.run(_recreate_database())
    _migrate()
    if GRANTS_SQL is None:
        raise RuntimeError("db/grants.sql not found — the suite verifies it against the schema")
    asyncio.run(_apply_grants())


@pytest.fixture(autouse=True)
async def clean_tables(database: None) -> AsyncIterator[None]:
    """Truncate before, not after: a failed test leaves its rows behind to look at."""
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield
    # Each test runs in its own event loop, and a pooled asyncpg connection
    # belongs to the loop that opened it. The pool must not outlive the test.
    await engine.dispose()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as db_session:
        yield db_session


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    """The REST surface, in-process. No lifespan needed — only FastMCP's mounted
    app wants one, and the MCP tests go in-memory rather than over HTTP."""
    from annos.app import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def mcp_client() -> AsyncIterator[Client]:
    """The MCP surface over the in-memory transport: real tool dispatch and real
    serialisation, no socket. With no HTTP request in scope `get_http_headers()`
    returns nothing, so identity falls to ANNOS_DEV_SUBJECT."""
    from annos.adapters.mcp import mcp

    async with Client(mcp) as client:
        yield client


@pytest.fixture
def make_food(session: AsyncSession) -> Callable[..., Awaitable[Food]]:
    async def _make(
        name: str,
        *,
        name_fi: str | None = None,
        source: str = "fineli",
        owner_id: str | None = None,
        kcal: float = 100,
        protein_g: float = 5,
        carbs_g: float = 10,
        fat_g: float = 2,
        fiber_g: float | None = None,
        serving_units: tuple[tuple[str, float], ...] = (),
    ) -> Food:
        food = Food(
            name=name,
            name_fi=name_fi,
            source=source,
            owner_id=owner_id,
            kcal=kcal,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
            fiber_g=fiber_g,
            serving_units=[ServingUnit(name=unit, grams=grams) for unit, grams in serving_units],
        )
        session.add(food)
        await session.commit()
        return food

    return _make
