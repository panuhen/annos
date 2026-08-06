"""Profile read and write.

`coaching_notes` is stored and returned verbatim. The server never interprets
it — that string is effectively the user's system prompt, and interpreting it
here would pull judgment server-side, which is explicitly rejected.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from annos import nickname as nickname_mod
from annos import servertime
from annos.models import CoachingNoteRevision, UserProfile

# Fields a caller may change. `nickname` and `subject` are absent on purpose:
# there is no rename surface anywhere in the product, and identity comes from
# the token rather than from any payload.
UPDATABLE = frozenset(
    {
        "birth_year",
        "height_cm",
        "sex",
        "activity_baseline",
        "timezone",
        "units",
        "language",
        "ui_language",
        "show_item_macros",
        "dietary_prefs",
        "coaching_notes",
    }
)


class ProfileNotFound(Exception):
    """No profile row for this subject — registration never completed."""


class AlreadyRegistered(Exception):
    """This subject already completed registration; there is nothing to create."""

    def __init__(self, subject: str) -> None:
        super().__init__("already registered")
        self.subject = subject


class UnknownField(Exception):
    def __init__(self, names: set[str]) -> None:
        super().__init__(f"not updatable: {', '.join(sorted(names))}")
        self.names = names


class InvalidValue(Exception):
    """A recognised field carrying a value the profile cannot hold."""


def _validate(changes: dict) -> None:
    """Refuse impossible values on both surfaces — the web UI offers only
    valid options, but an MCP client can send anything. Mirrors (and fronts)
    the database checks, so a bad value is a clean 422 rather than a
    constraint error."""
    tz = changes.get("timezone")
    if tz is not None:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise InvalidValue(f"unknown timezone: {tz!r}") from exc
    birth_year = changes.get("birth_year")
    if birth_year is not None and not (isinstance(birth_year, int) and 1900 <= birth_year <= 2100):
        raise InvalidValue("birth_year must be a year between 1900 and 2100")
    height = changes.get("height_cm")
    if height is not None and not (isinstance(height, int) and 50 <= height <= 300):
        raise InvalidValue("height_cm must be between 50 and 300")
    show_macros = changes.get("show_item_macros")
    if show_macros is not None and not isinstance(show_macros, bool):
        raise InvalidValue("show_item_macros must be true or false")


async def get_profile(session: AsyncSession, *, subject: str) -> UserProfile:
    profile = await session.scalar(select(UserProfile).where(UserProfile.subject == subject))
    if profile is None:
        raise ProfileNotFound(subject)
    return profile


async def create_profile(
    session: AsyncSession, *, subject: str, nickname: str | None = None
) -> UserProfile:
    """Complete registration for a subject Better Auth has already created.

    Called from the REST adapter only — registration is UI-only, so there is no
    MCP tool for this.
    """
    # The pre-check gives the common double-submit a clean answer; the
    # IntegrityError below is the backstop for the race the check can't close
    # (subject is the primary key, so the constraint always has the last word).
    if await session.scalar(select(UserProfile).where(UserProfile.subject == subject)):
        raise AlreadyRegistered(subject)
    try:
        profile = await nickname_mod.claim(session, subject=subject, nickname=nickname)
    except IntegrityError as exc:
        if _is_subject_conflict(exc):
            raise AlreadyRegistered(subject) from exc
        raise
    await session.commit()
    return profile


def _is_subject_conflict(exc: IntegrityError) -> bool:
    constraint = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
    if constraint:
        return "pkey" in constraint
    return "pkey" in str(exc.orig)


async def update_profile(session: AsyncSession, *, subject: str, changes: dict) -> UserProfile:
    """Partial update. Rejects unknown or non-updatable fields loudly.

    Silently dropping an unrecognised field would let a client believe it had
    changed a setting it hadn't.
    """
    unknown = set(changes) - UPDATABLE
    if unknown:
        raise UnknownField(unknown)
    _validate(changes)

    profile = await get_profile(session, subject=subject)
    # Coaching notes keep their history: every actual change appends what the
    # notes *became*. A rewrite to the same text is not a revision, and the
    # history is read only by coaching_notes_history — never by default.
    if "coaching_notes" in changes and changes["coaching_notes"] != profile.coaching_notes:
        session.add(CoachingNoteRevision(subject=subject, notes=changes["coaching_notes"]))
    for name, value in changes.items():
        setattr(profile, name, value)
    await session.commit()
    await session.refresh(profile)
    return profile


async def coaching_notes_history(session: AsyncSession, *, subject: str) -> dict:
    """Every version the coaching notes have been, newest first.

    The current value lives on the profile and rides along in every default
    payload; this exists only for the explicit "how have my instructions
    changed" question. A null `notes` records the notes being cleared.
    """
    profile = await get_profile(session, subject=subject)
    revisions = await session.scalars(
        select(CoachingNoteRevision)
        .where(CoachingNoteRevision.subject == subject)
        .order_by(CoachingNoteRevision.created_at.desc(), CoachingNoteRevision.id.desc())
    )
    return {
        "revisions": [
            {"notes": revision.notes, "set_at": revision.created_at.isoformat()}
            for revision in revisions
        ],
        "server_time": servertime.echo(profile.timezone),
    }
