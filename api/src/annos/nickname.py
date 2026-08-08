"""Nickname generation — the only display identity anywhere in Annos.

Structural privacy, not policy: nicknames are always generated, never
user-supplied. Self-chosen names are how real names and cross-service handles
leak into the identity layer. The registration UI only ever submits rolled
candidates, but the REST endpoint is reachable with any bearer token, so the
guarantee is enforced here: a candidate is accepted only if every word of it
comes from the generator's own vocabulary. It also disposes of the
offensive-name moderation problem for free.

Annos owns the nickname, not Better Auth. The generator lives next to the UNIQUE
constraint and the retry loop, which is the only place that can resolve a
collision correctly.
"""

import re
from functools import lru_cache
from pathlib import Path

import coolname
from coolname import generate_slug
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from annos.models import UserProfile

# ~10^10 combinations from three words ("nimble-copper-heron"); collisions are
# theoretical, but the insert below still handles them rather than assuming.
_WORDS = 3
_MAX_ATTEMPTS = 5

# Three concepts render as three or four hyphenated words (a third of the
# slugs carry a connector: "obedient-adder-from-saturn").
_SHAPE = re.compile(r"[a-z]+(?:-[a-z]+){2,3}")


@lru_cache(maxsize=1)
def _vocabulary() -> frozenset[str]:
    """Every word the generator can emit, read from coolname's own wordlists.

    A candidate whose words all come from this set is indistinguishable from a
    rolled one — which is the actual requirement. Verifying the exact slug was
    rolled would need server-side state; verifying the vocabulary needs none.
    """
    data_dir = Path(coolname.__file__).parent / "data"
    words: set[str] = set()
    for path in data_dir.glob("*.txt"):
        for line in path.read_text().splitlines():
            line = line.strip()
            # Skip comments and option lines ("max_length = 24"); word lines
            # may carry multi-word phrases that hyphenate in the slug.
            if not line or line.startswith("#") or "=" in line:
                continue
            words.update(line.split())
    # Connectors come from the phrase config, not the wordlists.
    words |= {"of", "from"}
    return frozenset(words)


class InvalidNickname(Exception):
    """The candidate could not have come from the generator."""

    def __init__(self, nickname: str) -> None:
        super().__init__("nickname must be a generated candidate")
        self.nickname = nickname


def validate_candidate(nickname: str) -> None:
    if not _SHAPE.fullmatch(nickname) or any(
        word not in _vocabulary() for word in nickname.split("-")
    ):
        raise InvalidNickname(nickname)


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
    whatever the generator produces first. A supplied candidate must pass the
    vocabulary check — the UI only submits rolled names, but this endpoint is
    reachable by any client and "generated only" has to hold server-side.
    """
    if nickname is not None:
        validate_candidate(nickname)
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
