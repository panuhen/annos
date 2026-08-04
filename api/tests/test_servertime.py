"""The server owns time.

AI clients don't reliably know the date mid-conversation, so nothing here takes
a client-supplied clock, and the day boundary is defined in one place.
"""

from datetime import UTC, datetime

from annos import servertime


def test_now_is_timezone_aware_utc():
    """Everything is stored in UTC; a naive datetime would silently take on the
    server's local zone."""
    moment = servertime.now()

    assert moment.tzinfo is not None
    assert moment.utcoffset().total_seconds() == 0


def test_a_late_night_snack_lands_on_the_new_day():
    """00:30 in Helsinki is the next calendar day, and that is the whole rule —
    no 3 a.m. rollover cleverness. Corrections handle the rest."""
    at = datetime(2026, 8, 4, 21, 30, tzinfo=UTC)  # 00:30 on the 5th in Helsinki

    assert servertime.local_date("Europe/Helsinki", at) == "2026-08-05"
    assert servertime.local_date("UTC", at) == "2026-08-04"


def test_the_day_boundary_follows_the_users_timezone():
    at = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)

    assert servertime.local_date("Pacific/Auckland", at) == "2026-08-05"
    assert servertime.local_date("America/Los_Angeles", at) == "2026-08-04"


def test_echo_carries_the_local_date_not_just_the_instant():
    """The block every response ships. A client that reads it never has to
    guess what day it is."""
    echoed = servertime.echo("Europe/Helsinki")

    assert set(echoed) == {"utc", "timezone", "local_date"}
    assert echoed["timezone"] == "Europe/Helsinki"
    assert datetime.fromisoformat(echoed["utc"]).tzinfo is not None
    assert echoed["local_date"] == servertime.local_date("Europe/Helsinki")
