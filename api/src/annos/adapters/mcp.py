"""MCP adapter — what AI clients call.

Tools take structured inputs only, never natural language: the client does all
disambiguation and constraint reasoning before calling. Every response carries
`server_time` so the client is re-anchored on each call.

No tool accepts a user id. Identity is resolved from the request's bearer token,
so a confused client cannot reach another user's data.
"""

from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider, TokenVerifier
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.dependencies import get_http_headers
from pydantic import AnyHttpUrl

from annos import servertime
from annos.config import settings
from annos.db import SessionLocal
from annos.domain import foods as foods_domain
from annos.domain import profile as profile_domain
from annos.identity import AuthError, Caller, resolve_caller


class IdentityTokenVerifier(TokenVerifier):
    """Adapts resolve_caller() to FastMCP's auth middleware.

    When this returns None, the middleware answers HTTP 401 with a
    WWW-Authenticate header naming the protected-resource metadata — the
    handshake a remote MCP client uses to discover Better Auth and start the
    OAuth flow. Without it, a bad token would surface as a JSON-RPC tool error
    over HTTP 200 and no client would ever reach the login page.

    Identity still lives in annos.identity; validating here warms the same
    cache the tools read through, so a request costs one upstream call, not two.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            caller = await resolve_caller(f"Bearer {token}")
        except AuthError:
            return None
        return AccessToken(token=token, client_id=caller.subject, subject=caller.subject, scopes=[])


auth_provider = RemoteAuthProvider(
    token_verifier=IdentityTokenVerifier(),
    # The authorization server's browser-facing origin: RFC 8414 discovery for
    # it lives at {origin}/.well-known/oauth-authorization-server, which the
    # Next.js app serves.
    authorization_servers=[AnyHttpUrl(settings.auth_jwt_issuer)],
    base_url=f"{settings.public_base_url}/mcp",
    resource_name="annos",
)

mcp: FastMCP = FastMCP(
    name="annos",
    auth=auth_provider,
    instructions=(
        "Annos logs meals, training, and bodyweight. Portions are in grams. "
        "Resolve foods with find_food before logging anything, and ask before "
        "assuming a meal type. Food names exist in Finnish, Swedish and English; "
        "search works in all three and results come back in the language set on "
        "the user's profile. Food data from the Finnish Institute for Health "
        "and Welfare, Fineli (CC-BY 4.0)."
    ),
)


async def _caller() -> Caller:
    # `include` is load-bearing. get_http_headers() drops `authorization` from
    # its default result — sensible for a proxy forwarding headers onwards,
    # wrong for us, since that header *is* the identity. Without this, every
    # call arrives anonymous and 401s the moment ANNOS_DEV_SUBJECT is unset.
    headers = get_http_headers(include={"authorization"})
    return await resolve_caller(headers.get("authorization"))


@mcp.tool
async def find_food(query: str, limit: int = 10) -> dict[str, Any]:
    """Search foods by name, in Finnish, Swedish or English.

    All three are searched whatever language the user is speaking, so a query in
    any of them finds the food. Results come back in the language on this
    account's profile; `name_language` says which language each name is actually
    in, since not every food has all three.

    Returns candidates with per-100g macros and serving units, so grams can be
    computed before logging. Searches the global Fineli/verified catalogue plus
    foods this account created.
    """
    who = await _caller()
    async with SessionLocal() as session:
        language = await foods_domain.reading_language(session, subject=who.subject)
        candidates = await foods_domain.find_food(
            session, subject=who.subject, query=query, limit=limit
        )
    return {
        "results": [foods_domain.candidate_payload(c, language) for c in candidates],
        "language": language,
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
            "language": profile.language,
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
