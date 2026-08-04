"""Constraints the database enforces, and the grants that quarantine the email.

These are checks on the migrated schema itself rather than on Python. Every one
of them is a rule the application layer must be unable to talk its way around.
"""

import asyncpg
import pytest
from sqlalchemy import text

from annos.db import Base, engine
from conftest import URL, dsn

INSERT_FOOD = (
    "INSERT INTO foods (name_fi, source, kcal, protein_g, carbs_g, fat_g) "
    "VALUES (:name, :source, 100, 5, 10, 2)"
)

# Shaped like the tables Better Auth creates in this same database. The real
# ones arrive via its own CLI, which has never been run here.
BETTER_AUTH_USER = 'CREATE TABLE "user" (id text PRIMARY KEY, email text NOT NULL)'


async def test_food_source_enum_rejects_an_unknown_value():
    """Provenance is a closed set. Postgres refuses anything outside it, so a
    guessed macro can never be filed as measured."""
    async with engine.begin() as conn:
        with pytest.raises(Exception, match="invalid input value for enum food_source"):
            await conn.execute(text(INSERT_FOOD), {"name": "Rahka", "source": "bogus"})


@pytest.mark.parametrize("source", ["fineli", "verified", "user", "label", "ai_estimate"])
async def test_every_declared_source_is_accepted(source):
    async with engine.begin() as conn:
        await conn.execute(text(INSERT_FOOD), {"name": f"Rahka {source}", "source": source})


@pytest.mark.parametrize("birth_year", [1899, 2101])
async def test_birth_year_must_be_plausible(birth_year):
    """A year, never a date of birth: age to the year is all Mifflin-St Jeor
    needs, and a birthday would be personal data collected for nothing."""
    async with engine.begin() as conn:
        with pytest.raises(Exception, match="ck_profile_birth_year"):
            await conn.execute(
                text(
                    "INSERT INTO user_profile (subject, nickname, birth_year) VALUES (:s, :n, :y)"
                ),
                {"s": "s1", "n": "n1", "y": birth_year},
            )


async def test_a_food_must_have_a_name_in_some_language():
    """All three name columns are nullable so a label photo can produce just
    one, but a row with none of them is not a food."""
    async with engine.begin() as conn:
        with pytest.raises(Exception, match="ck_foods_has_a_name"):
            await conn.execute(
                text(
                    "INSERT INTO foods (source, kcal, protein_g, carbs_g, fat_g) "
                    "VALUES ('user', 100, 5, 10, 2)"
                )
            )


@pytest.mark.parametrize("language", ["fi", "sv", "en"])
async def test_any_single_language_is_enough(language):
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"INSERT INTO foods (name_{language}, source, kcal, protein_g, carbs_g, fat_g) "
                "VALUES ('Something', 'user', 100, 5, 10, 2)"
            )
        )


async def test_profile_language_is_constrained():
    async with engine.begin() as conn:
        with pytest.raises(Exception, match="ck_profile_language"):
            await conn.execute(
                text(
                    "INSERT INTO user_profile (subject, nickname, language) "
                    "VALUES ('s1', 'n1', 'de')"
                )
            )


async def test_sex_is_constrained():
    async with engine.begin() as conn:
        with pytest.raises(Exception, match="ck_profile_sex"):
            await conn.execute(
                text("INSERT INTO user_profile (subject, nickname, sex) VALUES (:s, :n, 'yes')"),
                {"s": "s1", "n": "n1"},
            )


async def test_nickname_is_unique_at_the_database():
    """The constraint is what makes the retry loop in nickname.py correct; a
    uniqueness check in Python would race."""
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO user_profile (subject, nickname) VALUES ('s1', 'same-name-twice')")
        )
        with pytest.raises(Exception, match="nickname"):
            await conn.execute(
                text(
                    "INSERT INTO user_profile (subject, nickname) VALUES ('s2', 'same-name-twice')"
                )
            )


# --- the email quarantine ---------------------------------------------------


@pytest.mark.parametrize("table", sorted(Base.metadata.tables))
async def test_grants_cover_every_annos_table(table):
    """db/grants.sql enumerates tables by hand, on purpose: ALTER DEFAULT
    PRIVILEGES would have handed annos_api every future table the owner
    creates, Better Auth's included. The cost is that a new table must be added
    to that file, and this is where forgetting shows up."""
    conn = await asyncpg.connect(dsn(URL.database, username="annos_api", password="annos"))
    try:
        await conn.execute(f'SELECT 1 FROM "{table}" LIMIT 1')
    finally:
        await conn.close()


async def test_the_api_role_cannot_read_better_auths_user_table():
    """The quarantine itself. Column encryption was considered and rejected;
    this grant is the whole mechanism, so it gets a test rather than trust."""
    async with engine.begin() as conn:
        await conn.execute(text(BETTER_AUTH_USER))
        await conn.execute(text("INSERT INTO \"user\" VALUES ('u1', 'panu@example.com')"))

    api_conn = await asyncpg.connect(dsn(URL.database, username="annos_api", password="annos"))
    try:
        # Positive control first: the role works, it is only this table it can't see.
        await api_conn.execute("SELECT 1 FROM foods LIMIT 1")

        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await api_conn.fetchval('SELECT email FROM "user"')
    finally:
        await api_conn.close()
        async with engine.begin() as conn:
            await conn.execute(text('DROP TABLE "user"'))
