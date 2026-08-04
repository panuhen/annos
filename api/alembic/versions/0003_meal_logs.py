"""Meal logging: one row per eating event, macros snapshotted per item

`meal_log_items` copies the per-100g macros at log time. Food definitions
change; history must not. Per-100g rather than per-portion, so a grams-only
revision can rescale from the snapshot without touching the (possibly
since-edited) food row.

Which calendar day a log counts toward is not stored — the profile timezone
decides it at read time. See the Time handling note.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Native enums, created explicitly with create_type=False — the default *plus*
# an explicit .create() would emit CREATE TYPE twice. test_migrations pins this.
MEALS = ("breakfast", "lunch", "dinner", "snack")
INPUT_MODES = ("text", "photo", "plan")

meal_type = postgresql.ENUM(*MEALS, name="meal_type", create_type=False)
input_mode = postgresql.ENUM(*INPUT_MODES, name="input_mode", create_type=False)


def upgrade() -> None:
    meal_type.create(op.get_bind(), checkfirst=True)
    input_mode.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "meal_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        # The Better Auth user id, same convention as user_profile.subject:
        # opaque text, no foreign key into the auth schema.
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # Nullable: "the user didn't say" is representable, and the client is
        # told to ask rather than assume.
        sa.Column("meal", meal_type, nullable=True),
        sa.Column("input_mode", input_mode, nullable=False, server_default="text"),
        sa.Column("planned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_meal_logs_subject_ts", "meal_logs", ["subject", "ts"])

    op.create_table(
        "meal_log_items",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "log_id",
            sa.Integer(),
            sa.ForeignKey("meal_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("food_id", sa.Integer(), sa.ForeignKey("foods.id"), nullable=False),
        sa.Column("grams", sa.Numeric(8, 2), nullable=False),
        # Per-100g snapshot, same shape and names as foods.
        sa.Column("kcal", sa.Numeric(8, 2), nullable=False),
        sa.Column("protein_g", sa.Numeric(8, 2), nullable=False),
        sa.Column("carbs_g", sa.Numeric(8, 2), nullable=False),
        sa.Column("fat_g", sa.Numeric(8, 2), nullable=False),
        sa.Column("fiber_g", sa.Numeric(8, 2), nullable=True),
        sa.CheckConstraint("grams > 0", name="ck_meal_log_items_grams_positive"),
    )
    op.create_index("ix_meal_log_items_log_id", "meal_log_items", ["log_id"])


def downgrade() -> None:
    op.drop_index("ix_meal_log_items_log_id", table_name="meal_log_items")
    op.drop_table("meal_log_items")
    op.drop_index("ix_meal_logs_subject_ts", table_name="meal_logs")
    op.drop_table("meal_logs")
    input_mode.drop(op.get_bind(), checkfirst=True)
    meal_type.drop(op.get_bind(), checkfirst=True)
