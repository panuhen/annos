"""Exercise logging: the MET catalog, sessions, and strength sets

Four tables (see the Schema — exercise note, revised 2026-08-07):

* `activities` — the Compendium of Physical Activities MET catalog, seeded
  once from `data/activities.csv` by `annos.seed_activities`. English-only by
  decision; trigram-indexed like food names.
* `exercises` — strength movements, user-grown and user-scoped (one user's
  "penkki" never leaks into another's catalog), unique per owner
  case-insensitively.
* `exercise_logs` — one row per session, with the bodyweight snapshot the
  kcal estimate was computed from (same discipline as macro snapshots) and
  the estimate itself, NULL whenever a factor is honestly unknown.
* `strength_sets` — one row per set; weight 0 is a bodyweight set.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

exercise_kind = sa.Enum("cardio", "strength", "other", name="exercise_kind")
exercise_source = sa.Enum("user", "ai_estimate", name="exercise_source")


def upgrade() -> None:
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=5), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("met", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.CheckConstraint("met > 0", name="ck_activities_met_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "ix_activities_name_trgm",
        "activities",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("muscle_group", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_exercises_owner_lower_name",
        "exercises",
        ["owner_id", sa.literal_column("lower(name)")],
        unique=True,
    )

    op.create_table(
        "exercise_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column(
            "ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("kind", exercise_kind, nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("duration_min", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("kcal_estimate", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("planned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source", exercise_source, server_default="user", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "duration_min IS NULL OR duration_min > 0", name="ck_exercise_logs_duration_positive"
        ),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exercise_logs_subject_ts", "exercise_logs", ["subject", "ts"], unique=False)

    op.create_table(
        "strength_sets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("log_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("set_no", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("rpe", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.CheckConstraint("reps > 0", name="ck_strength_sets_reps_positive"),
        sa.CheckConstraint("rpe IS NULL OR (rpe >= 1 AND rpe <= 10)", name="ck_strength_sets_rpe"),
        sa.CheckConstraint("weight_kg >= 0", name="ck_strength_sets_weight_not_negative"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"]),
        sa.ForeignKeyConstraint(["log_id"], ["exercise_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_strength_sets_exercise_id", "strength_sets", ["exercise_id"], unique=False)
    op.create_index("ix_strength_sets_log_id", "strength_sets", ["log_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_strength_sets_log_id", table_name="strength_sets")
    op.drop_index("ix_strength_sets_exercise_id", table_name="strength_sets")
    op.drop_table("strength_sets")
    op.drop_index("ix_exercise_logs_subject_ts", table_name="exercise_logs")
    op.drop_table("exercise_logs")
    op.drop_index("uq_exercises_owner_lower_name", table_name="exercises")
    op.drop_table("exercises")
    op.drop_index(
        "ix_activities_name_trgm",
        table_name="activities",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_table("activities")
    exercise_source.drop(op.get_bind(), checkfirst=True)
    exercise_kind.drop(op.get_bind(), checkfirst=True)
