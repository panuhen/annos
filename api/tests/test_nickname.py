"""Nickname generation and the collision retry.

Nicknames are generated, never user-supplied — an input field that doesn't exist
can't leak a real name. What the user *can* do is re-roll during registration and
commit a candidate, which is why `claim` distinguishes "the generator collided,
try again" from "the name you picked is taken, here's an error".
"""

import re

import pytest

from annos import nickname as nickname_mod
from annos.domain import profile as profile_domain
from conftest import OTHER_SUBJECT, SUBJECT


def test_roll_returns_a_lowercase_hyphenated_slug():
    """Three concepts, but not always three words: coolname renders a third of
    them with a connector ("obedient-adder-from-saturn"). Anything relying on a
    fixed word count would fail a third of the time."""
    slugs = [nickname_mod.roll() for _ in range(50)]

    assert all(re.fullmatch(r"[a-z]+(?:-[a-z]+){2,}", slug) for slug in slugs)


def test_roll_varies():
    """A generator stuck on one value would make every registration after the
    first collide, and the retry loop would then exhaust its attempts."""
    assert len({nickname_mod.roll() for _ in range(20)}) > 1


async def test_a_supplied_candidate_is_committed_as_is(session):
    profile = await profile_domain.create_profile(
        session, subject=SUBJECT, nickname="nimble-copper-heron"
    )

    assert profile.nickname == "nimble-copper-heron"


async def test_a_generated_collision_is_retried(session, monkeypatch):
    await profile_domain.create_profile(session, subject=SUBJECT, nickname="nimble-copper-heron")
    candidates = iter(["nimble-copper-heron", "swift-amber-otter"])
    monkeypatch.setattr(nickname_mod, "roll", lambda: next(candidates))

    profile = await profile_domain.create_profile(session, subject=OTHER_SUBJECT)

    assert profile.nickname == "swift-amber-otter"


async def test_a_supplied_collision_is_reported_not_substituted(session):
    """The user chose this one, so tell them it's taken rather than quietly
    handing them a different name."""
    await profile_domain.create_profile(session, subject=SUBJECT, nickname="nimble-copper-heron")

    with pytest.raises(nickname_mod.NicknameTaken) as exc:
        await profile_domain.create_profile(
            session, subject=OTHER_SUBJECT, nickname="nimble-copper-heron"
        )

    assert exc.value.nickname == "nimble-copper-heron"


async def test_a_duplicate_subject_is_not_mistaken_for_a_nickname_collision(session):
    """Registering the same subject twice is a double registration, not a name
    clash. The retry loop must not swallow it and hand back a second profile."""
    await profile_domain.create_profile(session, subject=SUBJECT)

    with pytest.raises(profile_domain.AlreadyRegistered):
        await profile_domain.create_profile(session, subject=SUBJECT)


async def test_rest_reports_a_taken_nickname_as_409(api, session):
    await profile_domain.create_profile(session, subject=OTHER_SUBJECT, nickname="taken-name-here")

    response = await api.post("/api/profile", json={"nickname": "taken-name-here"})

    assert response.status_code == 409
