"""Day-type marks and per-day-type protein targets

`day_types` stores the manual mark only: the user saying what the day is
beats any derivation, in both directions. Days without a row resolve at read
time (exercise-derived once that exists, rest until then) — the table never
records a default.

Protein splits into training/rest the way kcal always was: the existing
column becomes `protein_target_rest` and `protein_target_training` is
backfilled from it, so every old phase keeps meaning exactly what it said.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DAY_TYPES = ("training", "rest")

day_type = postgresql.ENUM(*DAY_TYPES, name="day_type", create_type=False)


def upgrade() -> None:
    day_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "day_types",
        sa.Column("subject", sa.Text(), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("day_type", day_type, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.alter_column("goal_phases", "protein_target_g", new_column_name="protein_target_rest")
    op.add_column("goal_phases", sa.Column("protein_target_training", sa.Integer(), nullable=True))
    op.execute("UPDATE goal_phases SET protein_target_training = protein_target_rest")
    op.alter_column("goal_phases", "protein_target_training", nullable=False)

    op.drop_constraint("ck_goal_phases_targets_positive", "goal_phases", type_="check")
    op.create_check_constraint(
        "ck_goal_phases_targets_positive",
        "goal_phases",
        "kcal_target_training > 0 AND kcal_target_rest > 0 "
        "AND protein_target_training > 0 AND protein_target_rest > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_goal_phases_targets_positive", "goal_phases", type_="check")
    op.drop_column("goal_phases", "protein_target_training")
    op.alter_column("goal_phases", "protein_target_rest", new_column_name="protein_target_g")
    op.create_check_constraint(
        "ck_goal_phases_targets_positive",
        "goal_phases",
        "kcal_target_training > 0 AND kcal_target_rest > 0 AND protein_target_g > 0",
    )
    op.drop_table("day_types")
    day_type.drop(op.get_bind(), checkfirst=True)
