"""Apply the annos_api grants (api/db/grants.sql) as the owner.

Runs on api startup, right after `alembic upgrade head` and before the app
serves — the Coolify deploy has no one-shot step, and nothing else applies the
grants outside the test suite. GRANT is idempotent, so re-running on every
container start (and after a migration that adds a table) is safe.

Grants are enumerated by hand rather than inherited via ALTER DEFAULT
PRIVILEGES, so Better Auth's tables never pick them up — see
db/init/01-roles.sh and test_grants_cover_every_annos_table. This uses the
owner connection (ANNOS_MIGRATION_DATABASE_URL); the app itself still connects
as the restricted annos_api role, so the email quarantine is unchanged.
"""

import asyncio
import os
from pathlib import Path

import asyncpg


def _grants_sql() -> str:
    here = Path(__file__).resolve()
    candidates = [
        Path("/app/db/grants.sql"),  # container: COPY db ./db
        here.parents[2] / "db" / "grants.sql",  # /app or repo/api
        Path.cwd() / "db" / "grants.sql",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text()
    raise FileNotFoundError(f"grants.sql not found (looked in {candidates})")


async def _main() -> None:
    # The owner role; alembic uses the same one. asyncpg wants the bare
    # postgresql:// scheme, not SQLAlchemy's +asyncpg driver suffix.
    url = os.environ.get("ANNOS_MIGRATION_DATABASE_URL") or os.environ["ANNOS_DATABASE_URL"]
    url = url.replace("+asyncpg", "")
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(_grants_sql())
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(_main())
