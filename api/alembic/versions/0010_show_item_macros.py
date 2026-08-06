"""Per-item macros are a reading preference

`show_item_macros` on user_profile, beside the other presentation choices
(language, ui_language, units). Defaults true — the sheet prints macros
unless the reader says otherwise. Presentation only: the summary payload
always carries the numbers, this records whether the web sheet prints them.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profile",
        sa.Column("show_item_macros", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("user_profile", "show_item_macros")
