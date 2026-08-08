"""portion estimated flag on meal_log_items

An item-level provenance axis, orthogonal to foods.source: source records where
a food's per-100g numbers came from, `estimated` records whether the logged
amount was measured or guessed. Defaults false so existing rows read as stated.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-08 15:31:21.842009

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meal_log_items",
        sa.Column("estimated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("meal_log_items", "estimated")
