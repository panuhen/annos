"""MCP adapter — what AI clients call.

Tools take structured inputs only, never natural language: the client does all
disambiguation and constraint reasoning before calling. Every response carries
`server_time` so the client is re-anchored on each call.

No tool accepts a user id. Identity is resolved from the request's bearer token,
so a confused client cannot reach another user's data.
"""

from typing import Any

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

from annos import servertime
from annos.db import SessionLocal
from annos.domain import foods as foods_domain
from annos.domain import profile as profile_domain
from annos.identity import Caller, resolve_caller

mcp: FastMCP = FastMCP(
    name="annos",
    instructions=(
        "Annos logs meals, training, and bodyweight. Portions are in grams. "
        "Resolve foods with find_food before logging anything, and ask before "
        "assuming a meal type. Food data from the Finnish Institute for Health "
        "and Welfare, Fineli (CC-BY 4.0)."
    ),
)


async def _caller() -> Caller:
    headers = get_http_headers()
    return await resolve_caller(headers.get("authorization"))


@mcp.tool
async def find_food(query: str, limit: int = 10) -> dict[str, Any]:
    """Search foods by name, in Finnish or English.

    Returns candidates with per-100g macros and serving units, so grams can be
    computed before logging. Searches the global Fineli/verified catalogue plus
    foods this account created.
    """
    who = await _caller()
    async with SessionLocal() as session:
        candidates = await foods_domain.find_food(
            session, subject=who.subject, query=query, limit=limit
        )
    return {
        "results": [foods_domain.candidate_payload(c) for c in candidates],
        "server_time": servertime.echo("UTC"),
    }


@mcp.tool
async def get_profile() -> dict[str, Any]:
    """Current stats, preferences, and standing coaching notes for this account.

    `coaching_notes` is the user's own standing instruction about how they want
    to be coached — follow it.
    """
    who = await _caller()
    async with SessionLocal() as session:
        profile = await profile_domain.get_profile(session, subject=who.subject)
        return {
            "nickname": profile.nickname,
            "birth_year": profile.birth_year,
            "height_cm": profile.height_cm,
            "sex": profile.sex,
            "timezone": profile.timezone,
            "units": profile.units,
            "profile_context": {
                "dietary_prefs": profile.dietary_prefs,
                "coaching_notes": profile.coaching_notes,
            },
            "server_time": servertime.echo(profile.timezone),
        }


@mcp.tool
async def update_profile(changes: dict[str, Any]) -> dict[str, Any]:
    """Change profile fields, including coaching_notes in the user's own words.

    The nickname cannot be changed — it is assigned once at registration.
    """
    who = await _caller()
    async with SessionLocal() as session:
        profile = await profile_domain.update_profile(session, subject=who.subject, changes=changes)
        return {
            "updated": sorted(changes),
            "server_time": servertime.echo(profile.timezone),
        }
