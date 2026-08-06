"""The web app's chrome language, per user

`ui_language` is separate from `language` on purpose: `language` decides which
of a food's three names is served (both surfaces), while `ui_language` is the
web UI's own chrome — an English app can still show foods as ruisleipä. NULL
means the user never chose, and the web negotiates from Accept-Language.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_profile", sa.Column("ui_language", sa.String(length=2), nullable=True))
    op.create_check_constraint(
        "ck_profile_ui_language",
        "user_profile",
        "ui_language IS NULL OR ui_language IN ('fi', 'sv', 'en')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_profile_ui_language", "user_profile", type_="check")
    op.drop_column("user_profile", "ui_language")
