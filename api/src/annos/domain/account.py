"""Account deletion — the Annos half of the two-sided erasure.

Deletion spans two owners with no foreign key between them: Better Auth's
tables (user, sessions, OAuth tokens — deleted by Better Auth itself in the
Next.js app, the only side with rights on them) and every Annos table keyed
by the subject, deleted here. This function is the Annos side, one
transaction, immediate and permanent — no soft delete, no grace period.
Deleted data persists only in encrypted backups until rotation.

The typed-nickname confirmation is checked *here*, not just in the form: the
server knows the nickname, so a request that doesn't is not the user
confirming — it is a bug or a stray client, and it deletes nothing.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import profile as profile_domain
from annos.models import (
    BodyMetric,
    CoachingNoteRevision,
    DayTypeMark,
    Exercise,
    ExerciseLog,
    Food,
    GoalPhase,
    MealLog,
    MealTemplate,
    UserProfile,
)


class NicknameMismatch(Exception):
    """The confirmation didn't match — nothing was deleted."""

    def __init__(self) -> None:
        super().__init__("the nickname does not match; nothing was deleted")


async def delete_account(session: AsyncSession, *, subject: str, nickname: str) -> dict:
    """Erase everything Annos holds for this subject. Permanent.

    Order is foreign-key-safe: logs and templates go before the foods their
    items reference (only the owner's own logs can reference a private food —
    the visibility filter in log_meal guarantees it), and exercise logs
    (cascading their sets) go before the movement catalog the sets point at.
    The row counts come back as a receipt — an erasure that can say what it
    erased is auditable, one that can't is a shrug.
    """
    profile = await profile_domain.get_profile(session, subject=subject)
    if nickname.strip() != profile.nickname:
        raise NicknameMismatch()
    tz = profile.timezone

    erased: dict[str, int] = {}
    for model, owner_column in (
        (MealLog, MealLog.subject),  # items cascade in the database
        (MealTemplate, MealTemplate.subject),  # items cascade
        (ExerciseLog, ExerciseLog.subject),  # sets cascade
        (Exercise, Exercise.owner_id),  # after the sets that referenced it
        (Food, Food.owner_id),  # after every item snapshot that referenced it
        (BodyMetric, BodyMetric.subject),
        (GoalPhase, GoalPhase.subject),
        (DayTypeMark, DayTypeMark.subject),
        (CoachingNoteRevision, CoachingNoteRevision.subject),
        (UserProfile, UserProfile.subject),
    ):
        result = await session.execute(delete(model).where(owner_column == subject))
        erased[model.__tablename__] = result.rowcount
    await session.commit()

    return {
        "deleted": True,
        "nickname": nickname.strip(),
        "erased": erased,
        "server_time": servertime.echo(tz),
    }


async def _remaining_rows(session: AsyncSession, subject: str) -> int:
    """Test helper: how many rows any Annos table still holds for a subject."""
    count = 0
    for model, owner_column in (
        (UserProfile, UserProfile.subject),
        (MealLog, MealLog.subject),
        (MealTemplate, MealTemplate.subject),
        (ExerciseLog, ExerciseLog.subject),
        (Exercise, Exercise.owner_id),
        (Food, Food.owner_id),
        (BodyMetric, BodyMetric.subject),
        (GoalPhase, GoalPhase.subject),
        (DayTypeMark, DayTypeMark.subject),
        (CoachingNoteRevision, CoachingNoteRevision.subject),
    ):
        rows = (await session.execute(select(model).where(owner_column == subject))).scalars()
        count += len(list(rows))
    return count
