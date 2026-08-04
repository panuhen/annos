"""Nickname generation — the only display identity anywhere in Annos.

Structural privacy, not policy: nicknames are always generated, never
user-supplied. Self-chosen names are how real names and cross-service handles
leak into the identity layer, and an input field that doesn't exist can't leak.
It also disposes of the offensive-name moderation problem for free.

Annos owns the nickname, not Better Auth. The generator lives next to the UNIQUE
constraint and the retry loop, which is the only place that can resolve a
collision correctly.
"""

from coolname import generate_slug
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from annos.models import UserProfile

# ~10^10 combinations from three words ("nimble-copper-heron"); collisions are
# theoretical, but the insert below still handles them rather than assuming.
_WORDS = 3
_MAX_ATTEMPTS = 5


def roll() -> str:
    """Generate one candidate nickname. Cheap and side-effect free.

    The registration flow calls this repeatedly so the user can re-roll until
    satisfied. After registration the nickname is permanent — there is no rename
    surface anywhere in the product.
    """
    return generate_slug(_WORDS)


async def claim(session: AsyncSession, subject: str, nickname: str | None = None) -> UserProfile:
    """Create a profile, resolving nickname collisions by regenerating.

    Pass `nickname` to commit a candidate the user picked; omit it to take
    whatever the generator produces first.
    """
    for attempt in range(_MAX_ATTEMPTS):
        candidate = nickname if (nickname and attempt == 0) else roll()
        profile = UserProfile(subject=subject, nickname=candidate)
        session.add(profile)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            if not _is_nickname_conflict(exc):
                raise
            # A caller-supplied nickname that collides is not retried silently —
            # the user chose it, so tell them rather than substituting one.
            if nickname and attempt == 0:
                raise NicknameTaken(candidate) from exc
            continue
        else:
            return profile

    raise RuntimeError(f"could not find a free nickname in {_MAX_ATTEMPTS} attempts")


class NicknameTaken(Exception):
    """The requested nickname is already in use."""

    def __init__(self, nickname: str) -> None:
        super().__init__(f"nickname already taken: {nickname}")
        self.nickname = nickname


def _is_nickname_conflict(exc: IntegrityError) -> bool:
    constraint = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
    if constraint:
        return "nickname" in constraint
    return "nickname" in str(exc.orig)
