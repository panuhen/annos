"""Coaching-notes history, append-only

One row per change of `user_profile.coaching_notes`: what the notes became,
and when. The current value stays on the profile and default reads never
touch this table — it answers only the explicit "how have my instructions
changed" question. `notes` is nullable because clearing the notes is itself
a revision worth remembering.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coaching_note_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_coaching_note_revisions_subject_created",
        "coaching_note_revisions",
        ["subject", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_coaching_note_revisions_subject_created", table_name="coaching_note_revisions"
    )
    op.drop_table("coaching_note_revisions")
