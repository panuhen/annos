"""Profile read and write.

`coaching_notes` is stored and returned verbatim. The server never interprets
it — that string is effectively the user's system prompt, and interpreting it
here would pull judgment server-side, which is explicitly rejected.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from annos import nickname as nickname_mod
from annos.models import UserProfile

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
        "dietary_prefs",
        "coaching_notes",
    }
)


class ProfileNotFound(Exception):
    """No profile row for this subject — registration never completed."""


class UnknownField(Exception):
    def __init__(self, names: set[str]) -> None:
        super().__init__(f"not updatable: {', '.join(sorted(names))}")
        self.names = names


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
    profile = await nickname_mod.claim(session, subject=subject, nickname=nickname)
    await session.commit()
    return profile


async def update_profile(session: AsyncSession, *, subject: str, changes: dict) -> UserProfile:
    """Partial update. Rejects unknown or non-updatable fields loudly.

    Silently dropping an unrecognised field would let a client believe it had
    changed a setting it hadn't.
    """
    unknown = set(changes) - UPDATABLE
    if unknown:
        raise UnknownField(unknown)

    profile = await get_profile(session, subject=subject)
    for name, value in changes.items():
        setattr(profile, name, value)
    await session.commit()
    await session.refresh(profile)
    return profile
