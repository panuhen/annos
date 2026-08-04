import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import annos.models  # noqa: F401  — import registers models on Base.metadata
from annos.config import settings
from annos.db import Base

config = context.config

# Migrations run as the owner role, not the restricted runtime role.
# Escape percent signs: ConfigParser would otherwise treat them as interpolation.
config.set_main_option("sqlalchemy.url", settings.alembic_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Better Auth manages its own tables in THIS SAME database under its default
# names (user, session, account, verification, oauthApplication,
# oauthAccessToken, oauthConsent). They are absent from Base.metadata, so
# without this filter `alembic revision --autogenerate` compares them against
# nothing and cheerfully emits op.drop_table('user').
#
# Do not remove this. See the "Auth — Better Auth as authorization server" note.
ANNOS_TABLES = frozenset(target_metadata.tables)


def include_object(object, name, type_, reflected, compare_to) -> bool:  # noqa: A002
    if type_ == "table":
        return name in ANNOS_TABLES
    # Indexes and constraints hang off a table; skip any belonging to a table
    # we don't own, or autogenerate would try to "fix" Better Auth's schema.
    parent = getattr(object, "table", None)
    return parent is None or parent.name in ANNOS_TABLES


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.alembic_url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
