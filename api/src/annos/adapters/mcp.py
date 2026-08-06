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
from annos.domain import body as body_domain
from annos.domain import foods as foods_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.domain import summary as summary_domain
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
            "ui_language": profile.ui_language,
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


@mcp.tool
async def log_meal(
    items: list[dict[str, Any]],
    meal: str | None = None,
    ts: str | None = None,
    input_mode: str = "text",
    notes: str | None = None,
) -> dict[str, Any]:
    """Log one eating event. Items are {food_id, grams} — resolve foods with
    find_food and compute grams first.

    Omit ts unless the user stated a time; the server's clock is authoritative
    and "I just ate" needs no timestamp. Backdating takes ISO 8601; a timestamp
    without an offset is read in the user's own timezone. meal is
    breakfast/lunch/dinner/snack — ask rather than assume, or leave it out.
    input_mode "plan" records an intention, counted in no totals until
    revise_log confirms it with {"planned": false}.

    The response carries the updated day totals, so no follow-up call is needed
    to react to the new state of the day.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await meals_domain.log_meal(
            session,
            subject=who.subject,
            items=items,
            meal=meal,
            ts=ts,
            input_mode=input_mode,
            notes=notes,
        )


@mcp.tool
async def daily_summary(date: str | None = None) -> dict[str, Any]:
    """The whole day in one call: totals eaten, the active goal target,
    what remains, and the day's logs.

    No date means today, as the server defines it — never guess the date.
    `meals` carries log_ids so a correction can go straight to revise_log.
    Planned entries appear in the list but count toward no totals. day_type
    is "rest" until exercise logging exists, so the rest-day kcal target is
    the one in force. The numbers are facts; the judgment on them is yours,
    guided by profile_context.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await summary_domain.daily_summary(session, subject=who.subject, date=date)


@mcp.tool
async def log_weight(
    weight_kg: float | None = None,
    date: str | None = None,
    waist_cm: float | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Record bodyweight (kg) and/or waist (cm) for a day.

    One row per day: logging again the same day replaces the fields given and
    keeps the rest, so a morning weight and an evening waist coexist. Omit
    date unless the user stated one ("last Friday"); it defaults to today in
    their timezone. Daily fluctuation is noise — interpreting the trend is
    your job, not a reason to withhold a measurement.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await body_domain.log_weight(
            session,
            subject=who.subject,
            weight_kg=weight_kg,
            date=date,
            waist_cm=waist_cm,
            notes=notes,
        )


@mcp.tool
async def set_goal_phase(
    kind: str,
    kcal_training: int,
    kcal_rest: int,
    protein_g: int,
    rate_target: float | None = None,
    start_date: str | None = None,
) -> dict[str, Any]:
    """Start a new goal phase: deficit, maintenance, or surplus.

    kcal targets are per day type (training vs rest); protein_g is the daily
    protein target. rate_target is the intended weight change in kg/week,
    negative for loss. start_date defaults to today; the currently open phase
    is closed automatically the day before the new one starts. Past days keep
    being judged against the phase that was active then.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await body_domain.set_goal_phase(
            session,
            subject=who.subject,
            kind=kind,
            kcal_training=kcal_training,
            kcal_rest=kcal_rest,
            protein_g=protein_g,
            rate_target=rate_target,
            start_date=start_date,
        )


@mcp.tool
async def goal_history() -> dict[str, Any]:
    """Every goal phase ever set, newest first: what the targets were and when
    they changed.

    The open phase has end_date null; closed phases keep the targets they had,
    so the list reads as the user's goal progression. Past days are always
    judged against the phase in force then — daily_summary already does that,
    this is for reviewing the sequence itself.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await body_domain.list_goal_phases(session, subject=who.subject)


@mcp.tool
async def revise_log(log_id: int, changes: dict[str, Any]) -> dict[str, Any]:
    """Correct an existing meal log: "that was 250 g, not 400".

    changes may carry ts, meal, planned, notes, and/or items. items replaces
    the whole list — restate everything eaten, not just the changed row.
    {"planned": false} confirms a planned meal as eaten. There is no delete:
    a log that shouldn't exist gets its items corrected instead.

    Returns the revised log with that day's updated totals.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await meals_domain.revise_log(
            session, subject=who.subject, log_id=log_id, changes=changes
        )
