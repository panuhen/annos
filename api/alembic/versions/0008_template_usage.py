"""Template usage: what "the usual" actually is

`use_count` and `last_used_at` on meal_templates, bumped whenever a template
is expanded into a log. Template metadata only — logs never reference the
template, so this loses nothing history depends on. Lets every surface offer
the most-used templates first instead of guessing alphabetically.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meal_templates",
        sa.Column("use_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "meal_templates", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("meal_templates", "last_used_at")
    op.drop_column("meal_templates", "use_count")
