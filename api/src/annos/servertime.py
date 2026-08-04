"""The server is the time authority, never the client.

AI clients don't reliably know the current date mid-conversation. If the client
supplies timestamps, logs land on the wrong day. So every logging entry point
defaults to server `now()`, and every response echoes the server's own clock so
the client is re-anchored on every call.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def now() -> datetime:
    """Current instant, always timezone-aware UTC. Everything is stored in UTC."""
    return datetime.now(UTC)


def local_date(tz: str, at: datetime | None = None) -> str:
    """The calendar date in the user's timezone — the day-boundary definition.

    A 00:30 snack lands on the new day. If that's wrong for the user, the
    correction flow handles it; there are no clever 3 a.m. rollover rules.
    """
    moment = at or now()
    return moment.astimezone(ZoneInfo(tz)).date().isoformat()


def echo(tz: str) -> dict[str, str]:
    """The `server_time` block every response carries.

    Cheap, and it fixes the observed failure directly: a client that reads this
    never has to guess what day it is.
    """
    moment = now()
    return {
        "utc": moment.isoformat(),
        "timezone": tz,
        "local_date": local_date(tz, moment),
    }
