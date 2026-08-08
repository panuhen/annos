"""Ensure the runtime annos_api role exists, as the owner, before grants.

This is the startup twin of db/init/01-roles.sh. That script only runs on a
fresh Postgres volume's *first* start, and Coolify's compose deploy never
delivers the `./db/init` bind mount at all — so on the deployed stack the
annos_api role is simply never created, and `annos.apply_grants` then dies with
`UndefinedObjectError: role "annos_api" does not exist`. Creating the role here,
as the owner, right before grants, removes the reliance on the db-init mount.

Idempotent: creates the role only if absent, and always resets its password
from ANNOS_API_DB_PASSWORD so the env is the single source of truth (a rotated
password reconciles on the next start). Runs as the owner
(ANNOS_MIGRATION_DATABASE_URL); the app still connects as the restricted
annos_api role, so the email quarantine is unchanged. The explicit grants that
scope that role to Annos' own tables live in api/db/grants.sql — deliberately
NOT via ALTER DEFAULT PRIVILEGES, which would leak into Better Auth's tables.
"""

import asyncio
import os

import asyncpg


async def _main() -> None:
    # asyncpg wants the bare postgresql:// scheme, not the +asyncpg suffix.
    url = os.environ.get("ANNOS_MIGRATION_DATABASE_URL") or os.environ["ANNOS_DATABASE_URL"]
    url = url.replace("+asyncpg", "")
    api_pw = os.environ.get("ANNOS_API_DB_PASSWORD", "annos")

    conn = await asyncpg.connect(url)
    try:
        # Quote server-side: DDL can't take bind parameters, and a password may
        # contain anything, so let Postgres do the literal/identifier quoting.
        pw = await conn.fetchval("SELECT quote_literal($1::text)", api_pw)
        role = await conn.fetchval("SELECT quote_ident($1::text)", "annos_api")
        db = await conn.fetchval("SELECT quote_ident(current_database())")

        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", "annos_api")
        if exists:
            await conn.execute(f"ALTER ROLE {role} WITH LOGIN PASSWORD {pw}")
        else:
            await conn.execute(f"CREATE ROLE {role} LOGIN PASSWORD {pw}")

        await conn.execute(f"GRANT CONNECT ON DATABASE {db} TO {role}")
        await conn.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(_main())
