"""Profile domain rules, and the REST surface over them.

The load-bearing rule is that `update_profile` refuses anything outside
UPDATABLE. Silently dropping an unrecognised field would let a client report a
setting as changed when it wasn't — and `nickname` is the field a client is
most likely to try.
"""

import pytest

from annos.domain import profile as profile_domain
from conftest import SUBJECT


async def test_get_before_registration_raises(session):
    """Registration is REST-only, so a subject with a valid token can still have
    no row. That is a 404, not an empty profile."""
    with pytest.raises(profile_domain.ProfileNotFound):
        await profile_domain.get_profile(session, subject=SUBJECT)


async def test_create_then_get_round_trips(session):
    created = await profile_domain.create_profile(session, subject=SUBJECT)

    fetched = await profile_domain.get_profile(session, subject=SUBJECT)

    assert fetched.subject == SUBJECT
    assert fetched.nickname == created.nickname


async def test_registering_twice_is_refused(session):
    """The welcome flow retries and clients double-submit; the second attempt
    must be a clean refusal, not a constraint error dressed as a 500."""
    await profile_domain.create_profile(session, subject=SUBJECT)

    with pytest.raises(profile_domain.AlreadyRegistered):
        await profile_domain.create_profile(session, subject=SUBJECT)


async def test_defaults_are_set_by_the_database(session):
    profile = await profile_domain.create_profile(session, subject=SUBJECT)

    assert profile.timezone == "Europe/Helsinki"
    assert profile.units == "metric"
    assert profile.dietary_prefs == {}
    # NULL means "never chosen" — the web negotiates from Accept-Language.
    assert profile.ui_language is None


async def test_ui_language_updates_separately_from_language(session):
    """Two settings on purpose: an English app can still show ruisleipä."""
    await profile_domain.create_profile(session, subject=SUBJECT)

    updated = await profile_domain.update_profile(
        session, subject=SUBJECT, changes={"ui_language": "en"}
    )

    assert updated.ui_language == "en"
    assert updated.language == "fi"  # food names untouched


async def test_update_applies_changes(session):
    await profile_domain.create_profile(session, subject=SUBJECT)

    updated = await profile_domain.update_profile(
        session,
        subject=SUBJECT,
        changes={
            "birth_year": 1985,
            "height_cm": 181,
            "coaching_notes": "be blunt, no cheerleading",
            "dietary_prefs": {"exclude": ["dairy"]},
        },
    )

    assert updated.birth_year == 1985
    assert updated.height_cm == 181
    assert updated.coaching_notes == "be blunt, no cheerleading"
    assert updated.dietary_prefs == {"exclude": ["dairy"]}


async def test_update_rejects_nickname(session):
    """There is no rename surface anywhere in the product. The nickname is
    assigned once, at registration."""
    await profile_domain.create_profile(session, subject=SUBJECT)

    with pytest.raises(profile_domain.UnknownField) as exc:
        await profile_domain.update_profile(
            session, subject=SUBJECT, changes={"nickname": "chosen-by-me"}
        )

    assert exc.value.names == {"nickname"}


async def test_update_rejects_unknown_field_without_applying_the_rest(session):
    """All-or-nothing: a partially applied update is worse than a rejected one."""
    await profile_domain.create_profile(session, subject=SUBJECT)

    with pytest.raises(profile_domain.UnknownField):
        await profile_domain.update_profile(
            session, subject=SUBJECT, changes={"height_cm": 181, "shoe_size": 45}
        )

    profile = await profile_domain.get_profile(session, subject=SUBJECT)
    assert profile.height_cm is None


async def test_update_before_registration_raises(session):
    with pytest.raises(profile_domain.ProfileNotFound):
        await profile_domain.update_profile(session, subject=SUBJECT, changes={"height_cm": 181})


# --- REST surface -----------------------------------------------------------


async def test_coaching_notes_changes_append_to_the_history(session):
    await profile_domain.create_profile(session, subject=SUBJECT)
    await profile_domain.update_profile(
        session, subject=SUBJECT, changes={"coaching_notes": "be blunt"}
    )
    await profile_domain.update_profile(
        session, subject=SUBJECT, changes={"coaching_notes": "be gentle"}
    )

    history = await profile_domain.coaching_notes_history(session, subject=SUBJECT)

    assert [revision["notes"] for revision in history["revisions"]] == ["be gentle", "be blunt"]


async def test_rewriting_the_same_notes_is_not_a_revision(session):
    await profile_domain.create_profile(session, subject=SUBJECT)
    await profile_domain.update_profile(
        session, subject=SUBJECT, changes={"coaching_notes": "be blunt"}
    )
    await profile_domain.update_profile(
        session, subject=SUBJECT, changes={"coaching_notes": "be blunt", "height_cm": 181}
    )

    history = await profile_domain.coaching_notes_history(session, subject=SUBJECT)

    assert len(history["revisions"]) == 1


async def test_clearing_the_notes_is_a_revision(session):
    await profile_domain.create_profile(session, subject=SUBJECT)
    await profile_domain.update_profile(
        session, subject=SUBJECT, changes={"coaching_notes": "be blunt"}
    )
    await profile_domain.update_profile(session, subject=SUBJECT, changes={"coaching_notes": None})

    history = await profile_domain.coaching_notes_history(session, subject=SUBJECT)

    assert [revision["notes"] for revision in history["revisions"]] == [None, "be blunt"]


async def test_other_profile_changes_leave_the_history_alone(session):
    await profile_domain.create_profile(session, subject=SUBJECT)
    await profile_domain.update_profile(session, subject=SUBJECT, changes={"height_cm": 181})

    history = await profile_domain.coaching_notes_history(session, subject=SUBJECT)

    assert history["revisions"] == []


async def test_rest_get_profile_is_404_before_registration(api):
    response = await api.get("/api/profile")

    assert response.status_code == 404


async def test_rest_registration_flow(api):
    rolled = await api.post("/api/profile/nickname/roll")
    candidate = rolled.json()["nickname"]

    created = await api.post("/api/profile", json={"nickname": candidate})
    assert created.status_code == 201
    assert created.json()["nickname"] == candidate

    fetched = await api.get("/api/profile")
    assert fetched.status_code == 200
    assert fetched.json()["nickname"] == candidate


async def test_rest_double_registration_is_409(api):
    """The welcome page keys on 409 to say "already registered → home"."""
    assert (await api.post("/api/profile", json={})).status_code == 201

    second = await api.post("/api/profile", json={})

    assert second.status_code == 409
    assert second.json()["detail"] == "already registered"


async def test_rest_rolling_a_nickname_commits_nothing(api):
    """Re-rolling during registration must not create a row, or the user would
    be registered by browsing the name picker."""
    await api.post("/api/profile/nickname/roll")
    await api.post("/api/profile/nickname/roll")

    assert (await api.get("/api/profile")).status_code == 404


async def test_rest_serves_the_coaching_history(api):
    await api.post("/api/profile", json={})
    await api.patch("/api/profile", json={"changes": {"coaching_notes": "be blunt"}})

    response = await api.get("/api/profile/coaching-history")

    assert response.status_code == 200
    assert [r["notes"] for r in response.json()["revisions"]] == ["be blunt"]


async def test_rest_patch_rejects_nickname_with_422(api):
    await api.post("/api/profile", json={})

    response = await api.patch("/api/profile", json={"changes": {"nickname": "chosen-by-me"}})

    assert response.status_code == 422
    assert "nickname" in response.json()["detail"]


async def test_rest_profile_echoes_server_time(api):
    """Every response carries the server's clock, so a client is never guessing
    the date. Here it is in the user's own timezone."""
    await api.post("/api/profile", json={})

    payload = (await api.get("/api/profile")).json()

    assert payload["server_time"]["timezone"] == "Europe/Helsinki"
    assert set(payload["server_time"]) == {"utc", "timezone", "local_date"}
