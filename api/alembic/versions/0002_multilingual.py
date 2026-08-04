"""Native trilingual food data: fi/sv/en as peers, not translations

Fineli ships Finnish, Swedish and English complete for all 4 232 foods, so
`name` (implicitly English) plus `name_fi` was the wrong shape — it made one
language the real one. This renames it to `name_en` and adds `name_sv`, with a
trigram index each and a constraint that at least one survives.

Serving units lose their language entirely: `serving_units.name` held a word,
and now `unit_code` holds Fineli's code, rendered through the new
`serving_unit_types` thesaurus. `nutrient_components` does the same job for the
keys in `foods.micros`.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LANGUAGES = ("fi", "sv", "en")


def _trgm_index(lang: str) -> None:
    op.create_index(
        f"ix_foods_name_{lang}_trgm",
        "foods",
        [f"name_{lang}"],
        postgresql_using="gin",
        postgresql_ops={f"name_{lang}": "gin_trgm_ops"},
    )


def upgrade() -> None:
    # --- foods: three peer name columns -------------------------------------
    #
    # Rename rather than add-and-copy: the existing `name` column already holds
    # English, so renaming keeps the rows and the data means the same thing
    # afterwards.
    op.drop_index("ix_foods_name_trgm", table_name="foods")
    op.alter_column("foods", "name", new_column_name="name_en", nullable=True)
    op.add_column("foods", sa.Column("name_sv", sa.Text(), nullable=True))

    _trgm_index("en")
    _trgm_index("sv")

    op.create_check_constraint(
        "ck_foods_has_a_name", "foods", "num_nonnulls(name_fi, name_sv, name_en) > 0"
    )

    # --- serving units: a code, not a word ----------------------------------
    op.drop_constraint("uq_serving_units_food_name", "serving_units", type_="unique")
    op.alter_column("serving_units", "name", new_column_name="unit_code")
    op.create_unique_constraint(
        "uq_serving_units_food_unit", "serving_units", ["food_id", "unit_code"]
    )

    op.create_table(
        "serving_unit_types",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("name_fi", sa.Text(), nullable=True),
        sa.Column("name_sv", sa.Text(), nullable=True),
        sa.Column("name_en", sa.Text(), nullable=True),
    )

    op.create_table(
        "nutrient_components",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("class_code", sa.Text(), nullable=True),
        sa.Column("name_fi", sa.Text(), nullable=True),
        sa.Column("name_sv", sa.Text(), nullable=True),
        sa.Column("name_en", sa.Text(), nullable=True),
    )

    # --- which language a user reads in -------------------------------------
    op.add_column(
        "user_profile",
        sa.Column("language", sa.String(length=2), nullable=False, server_default="fi"),
    )
    op.create_check_constraint(
        "ck_profile_language", "user_profile", "language IN ('fi', 'sv', 'en')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_profile_language", "user_profile", type_="check")
    op.drop_column("user_profile", "language")

    op.drop_table("nutrient_components")
    op.drop_table("serving_unit_types")

    op.drop_constraint("uq_serving_units_food_unit", "serving_units", type_="unique")
    op.alter_column("serving_units", "unit_code", new_column_name="name")
    op.create_unique_constraint("uq_serving_units_food_name", "serving_units", ["food_id", "name"])

    op.drop_constraint("ck_foods_has_a_name", "foods", type_="check")
    op.drop_index("ix_foods_name_sv_trgm", table_name="foods")
    op.drop_index("ix_foods_name_en_trgm", table_name="foods")

    # Going back to a NOT NULL column: a row that only ever had a Finnish or
    # Swedish name cannot satisfy it, so fall back to whichever name exists
    # rather than failing the downgrade. Lossy in the same way the old schema
    # was lossy, which is the honest behaviour here. Must run before name_sv is
    # dropped, since it reads it.
    op.execute("UPDATE foods SET name_en = coalesce(name_en, name_fi, name_sv)")
    op.drop_column("foods", "name_sv")
    op.alter_column("foods", "name_en", new_column_name="name", nullable=False)
    op.create_index(
        "ix_foods_name_trgm",
        "foods",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
