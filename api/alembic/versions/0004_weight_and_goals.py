"""Body metrics and goal phases

`body_metrics` is one row per subject per day — logging weight twice on a day
upserts. The smoothed trend is computed at read time, never stored.

`goal_phases` gives targets a lifespan: end_date NULL is the current phase, a
new phase closes the previous one, and history evaluates each day against the
phase in force then.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GOAL_KINDS = ("deficit", "maintenance", "surplus")

goal_kind = postgresql.ENUM(*GOAL_KINDS, name="goal_kind", create_type=False)


def upgrade() -> None:
    goal_kind.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "body_metrics",
        sa.Column("subject", sa.Text(), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("weight_kg", sa.Numeric(5, 2), nullable=True),
        sa.Column("waist_cm", sa.Numeric(5, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "weight_kg IS NULL OR (weight_kg > 0 AND weight_kg < 500)",
            name="ck_body_metrics_weight_sane",
        ),
        sa.CheckConstraint(
            "waist_cm IS NULL OR (waist_cm > 0 AND waist_cm < 500)",
            name="ck_body_metrics_waist_sane",
        ),
        sa.CheckConstraint(
            "num_nonnulls(weight_kg, waist_cm, notes) > 0", name="ck_body_metrics_not_empty"
        ),
    )

    op.create_table(
        "goal_phases",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("kind", goal_kind, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("kcal_target_training", sa.Integer(), nullable=False),
        sa.Column("kcal_target_rest", sa.Integer(), nullable=False),
        sa.Column("protein_target_g", sa.Integer(), nullable=False),
        sa.Column("rate_target_kg_per_week", sa.Numeric(4, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "kcal_target_training > 0 AND kcal_target_rest > 0 AND protein_target_g > 0",
            name="ck_goal_phases_targets_positive",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="ck_goal_phases_dates"
        ),
    )
    op.create_index("ix_goal_phases_subject_start", "goal_phases", ["subject", "start_date"])


def downgrade() -> None:
    op.drop_index("ix_goal_phases_subject_start", table_name="goal_phases")
    op.drop_table("goal_phases")
    op.drop_table("body_metrics")
    goal_kind.drop(op.get_bind(), checkfirst=True)
