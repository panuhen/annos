"""MCP adapter — what AI clients call.

Tools take structured inputs only, never natural language: the client does all
disambiguation and constraint reasoning before calling. Every response carries
`server_time` so the client is re-anchored on each call.

No tool accepts a user id. Identity is resolved from the request's bearer token,
so a confused client cannot reach another user's data.
"""

from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider, TokenVerifier
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.dependencies import get_http_headers
from mcp.types import Icon
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import FileResponse

from annos import servertime
from annos.config import settings
from annos.db import SessionLocal
from annos.domain import body as body_domain
from annos.domain import days as days_domain
from annos.domain import exercise as exercise_domain
from annos.domain import export as export_domain
from annos.domain import foods as foods_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.domain import stats as stats_domain
from annos.domain import summary as summary_domain
from annos.domain import templates as templates_domain
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

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# The mark advertised to MCP clients in the server handshake (MCP's own `icons`
# field), served by the custom routes below. Both sit under the /mcp mount, so
# their public URLs are {origin}/mcp/…. The theme-adaptive SVG is listed first
# (a client that renders it gets the mark correct on light or dark chrome); the
# paper-white PNG is a raster fallback for clients that don't. Claude.ai today
# brands the connector from the OAuth authorization server's own page and
# favicon (the Next.js /consent route) rather than this field — this is the
# spec-correct mechanism regardless, for clients that read it.
_icon_base = f"{settings.public_base_url.rstrip('/')}/mcp"
MCP_ICONS = [
    Icon(src=f"{_icon_base}/favicon.svg", mimeType="image/svg+xml"),
    Icon(src=f"{_icon_base}/icon-128.png", mimeType="image/png", sizes=["128x128"]),
]

mcp: FastMCP = FastMCP(
    name="annos",
    auth=auth_provider,
    icons=MCP_ICONS,
    instructions=(
        "Annos logs meals, training, and bodyweight. Portions are in grams. "
        "Resolve foods with find_food before logging anything, and ask before "
        "assuming a meal type. Food names exist in Finnish, Swedish and English; "
        "search works in all three and results come back in the language set on "
        "the user's profile. The exercise activity catalog is English-only — "
        "translate before searching it ('juoksu' → 'running'); strength movement "
        "names are the user's own words in any language. Food data from the "
        "Finnish Institute for Health and Welfare, Fineli (CC-BY 4.0); MET values "
        "from the 2024 Adult Compendium of Physical Activities."
    ),
)


@mcp.custom_route("/favicon.svg", methods=["GET"])
async def favicon_svg(_request: Request) -> FileResponse:
    """The theme-adaptive Annos mark advertised in the MCP handshake."""
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@mcp.custom_route("/icon-128.png", methods=["GET"])
async def icon_png(_request: Request) -> FileResponse:
    """Raster (128px) fallback of the mark for clients that don't render SVG."""
    return FileResponse(STATIC_DIR / "icon-128.png", media_type="image/png")


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
    picks which of the phase's targets (kcal and protein) is in force;
    day_type_source says how it was resolved — "manual" is the user's own
    mark via set_day_type, "default" means unmarked days count as rest until
    exercise logging exists. The numbers are facts; the judgment on them is
    yours, guided by profile_context.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await summary_domain.daily_summary(session, subject=who.subject, date=date)


@mcp.tool
async def recent_meals(days: int = 7) -> dict[str, Any]:
    """What the user has been eating lately: the last days' meals (default 7,
    max 31), newest first, today included.

    This is the context call for "the usual", "same as Tuesday" or "what have
    I eaten this week" — each meal carries its local calendar date, its
    log_id (usable with revise_log and delete_log without having created the
    log in this conversation), and its items with food_ids and grams, so a
    past meal re-logs through log_meal with no find_food round trip. Planned
    entries are flagged planned. For one day's totals against its target,
    daily_summary is the call.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await summary_domain.recent_meals(session, subject=who.subject, days=days)


@mcp.tool
async def find_activity(query: str, limit: int = 10) -> dict[str, Any]:
    """Search the exercise activity catalog (Compendium of Physical
    Activities MET values) before calling log_exercise.

    The catalog is ENGLISH-ONLY: whatever language the user speaks, translate
    the activity into English before searching — "juoksu" or "löpning" is
    searched as "running", "kuntosali" as "resistance training". Returns
    candidates with their MET values; pick the one matching the user's stated
    intensity, or ask. Only cardio/other sessions need an activity — strength
    movements are named freely in the user's own words in log_exercise sets.
    """
    who = await _caller()
    async with SessionLocal() as session:
        results = await exercise_domain.find_activity(
            session, subject=who.subject, query=query, limit=limit
        )
    return {"results": results, "server_time": servertime.echo("UTC")}


@mcp.tool
async def log_exercise(
    kind: str,
    activity_id: int | None = None,
    duration_min: float | None = None,
    sets: list[dict[str, Any]] | None = None,
    ts: str | None = None,
    planned: bool = False,
    source: str = "user",
    notes: str | None = None,
) -> dict[str, Any]:
    """Log one training session. kind is cardio, strength, or other.

    Cardio/other: resolve activity_id with find_activity first (catalog is
    English-only — translate before searching); duration_min gives the kcal
    estimate, computed as MET x bodyweight x hours from the user's latest
    logged weight and null if they never logged one. Strength: sets as
    {exercise, reps, weight_kg, rpe?} — exercise is the user's own name for
    the movement in any language ("penkki" is fine), created on first
    mention; weight_kg 0 means a bodyweight set. Set source to "ai_estimate"
    when you guessed the duration or activity rather than the user stating it.

    Omit ts unless the user stated a time. planned records an intention that
    counts toward nothing until confirmed via revise_exercise. A non-planned
    session makes the day a training day (day_type "derived") unless the
    user's own mark says otherwise — the response carries the day's resolved
    type, so never call set_day_type just because a session was logged.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await exercise_domain.log_exercise(
            session,
            subject=who.subject,
            kind=kind,
            activity_id=activity_id,
            duration_min=duration_min,
            sets=sets,
            ts=ts,
            planned=planned,
            source=source,
            notes=notes,
        )


@mcp.tool
async def revise_exercise(log_id: int, changes: dict[str, Any]) -> dict[str, Any]:
    """Correct an existing exercise session: "that was 45 minutes, not 30".

    changes may carry ts, kind, activity_id, duration_min, planned, notes,
    and/or sets. sets replaces the whole list — restate every set, not just
    the changed one. {"planned": false} confirms a planned session, which is
    the moment it starts counting as training. The kcal estimate is
    recomputed from the bodyweight snapshotted when the session was logged.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await exercise_domain.revise_exercise(
            session, subject=who.subject, log_id=log_id, changes=changes
        )


@mcp.tool
async def delete_exercise(log_id: int) -> dict[str, Any]:
    """Erase an exercise session entirely — a duplicate, a test entry, a
    session that never happened. Permanent, sets and all.

    Use this only when the user explicitly asks for the session to be
    removed; a wrong duration or activity is revise_exercise. The response
    carries the day's re-resolved type — deleting the only session of a
    derived training day turns it back into a rest day.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await exercise_domain.delete_exercise(session, subject=who.subject, log_id=log_id)


@mcp.tool
async def set_day_type(day_type: str, date: str | None = None) -> dict[str, Any]:
    """Mark a day "training" or "rest" — the user's own say on which of the
    goal phase's targets the day gets.

    A manual mark always wins, in both directions: it gets training targets
    before the session is logged (or when the session happens outside Annos),
    and marks a day rest even if something later derives otherwise. Marking
    again replaces. Omit date unless the user stated one; it defaults to today
    in their timezone. Only call this when the user says what the day is —
    never infer it from the conversation.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await days_domain.set_day_type(
            session, subject=who.subject, day_type=day_type, date=date
        )


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
    protein_training: int,
    protein_rest: int,
    rate_target: float | None = None,
    start_date: str | None = None,
) -> dict[str, Any]:
    """Start a new goal phase: deficit, maintenance, or surplus.

    kcal and protein targets are per day type (training vs rest) — a user with
    one flat number gets it in both. rate_target is the intended weight change
    in kg/week and its sign must match the kind — negative for a deficit,
    positive for a surplus, omitted for maintenance. start_date defaults to
    today; the currently open phase is closed automatically the day before
    the new one starts. Past days keep being judged against the phase that
    was active then.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await body_domain.set_goal_phase(
            session,
            subject=who.subject,
            kind=kind,
            kcal_training=kcal_training,
            kcal_rest=kcal_rest,
            protein_training=protein_training,
            protein_rest=protein_rest,
            rate_target=rate_target,
            start_date=start_date,
        )


@mcp.tool
async def revise_goal_phase(changes: dict[str, Any]) -> dict[str, Any]:
    """Correct the open goal phase: kind, kcal_training, kcal_rest,
    protein_training, protein_rest, rate_target, and/or start_date.

    Only the open phase (end_date null) is revisable — closed phases are
    history and the days they judged keep them. Moving start_date also moves
    the previous phase's end to the day before, keeping the sequence gapless.
    Use set_goal_phase for a genuinely new phase; this is for "I set that up
    wrong".
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await body_domain.revise_goal_phase(session, subject=who.subject, changes=changes)


@mcp.tool
async def delete_goal_phase(phase_id: int) -> dict[str, Any]:
    """Erase a goal phase that should never have existed — a test entry, a
    phase opened by mistake.

    This is deletion, not correction, and it works on closed phases too:
    a mistake is not history, and left in place it blocks the open phase's
    start date. The days it claimed fall back to no target; neighbouring
    phases are never rewritten. "The targets are wrong" on the open phase is
    still revise_goal_phase. Only call this when the user explicitly says the
    phase should not exist; phase_ids come from goal_history.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await body_domain.delete_goal_phase(session, subject=who.subject, phase_id=phase_id)


@mcp.tool
async def coaching_history() -> dict[str, Any]:
    """Every version the user's coaching notes have been, newest first.

    Only for when the user asks how their coaching instructions have changed
    over time — the current notes already arrive in get_profile and in every
    profile_context block, so ordinary coaching never needs this call. A null
    notes entry records the notes being cleared at that moment.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await profile_domain.coaching_notes_history(session, subject=who.subject)


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


@mcp.tool
async def save_template(
    name: str,
    items: list[dict[str, Any]],
    total_grams: float | None = None,
) -> dict[str, Any]:
    """Save a meal as a reusable template: "the usual breakfast".

    Items are {food_id, grams} — resolve foods with find_food first. Saving
    an existing name replaces its contents; the name is how the user refers
    to it. total_grams turns the template into a recipe: the whole batch
    weighs this much, and logging can then take a stated number of grams.
    Templates store no macros — logging one snapshots that day's definitions.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await templates_domain.save_template(
            session, subject=who.subject, name=name, items=items, total_grams=total_grams
        )


@mcp.tool
async def revise_template(template_id: int, changes: dict[str, Any]) -> dict[str, Any]:
    """Correct a saved template by id: rename it, restate its items, or set
    or clear the recipe yield (total_grams).

    changes may carry name, items, and/or total_grams; items replaces the
    whole list, like revise_log. Find ids with list_templates. To simply
    replace the contents under an unchanged name, save_template also works.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await templates_domain.revise_template(
            session, subject=who.subject, template_id=template_id, changes=changes
        )


@mcp.tool
async def delete_template(template_id: int) -> dict[str, Any]:
    """Erase a saved template for good. Only when the user asks for it to be
    removed — meals already logged from it are untouched, they carry their
    own snapshots."""
    who = await _caller()
    async with SessionLocal() as session:
        return await templates_domain.delete_template(
            session, subject=who.subject, template_id=template_id
        )


@mcp.tool
async def list_templates() -> dict[str, Any]:
    """The saved templates, with items, current-definition kcal estimates,
    and template_ids for logging.

    Log one by putting {template_id, portions?} in log_meal's items —
    portions defaults to 1 (the whole template); {template_id, grams} takes
    that many grams of a recipe that has total_grams.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await templates_domain.list_templates(session, subject=who.subject)


@mcp.tool
async def delete_log(log_id: int) -> dict[str, Any]:
    """Erase a meal log entirely — a duplicate, a test entry, a meal that never
    happened. Permanent: the log and its snapshots are gone.

    Use this only when the user explicitly asks for the log to be removed.
    A wrong amount or wrong food is a correction, not a deletion — that is
    revise_log. Returns the day's totals after the removal.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await meals_domain.delete_log(session, subject=who.subject, log_id=log_id)


@mcp.tool
async def weekly_review(weeks: int = 4) -> dict[str, Any]:
    """How the plan is going, week by week: the one-call answer to "how's my
    cut/bulk going?".

    ISO weeks (Monday–Sunday, default 4, max 26), newest first, the current
    week flagged partial. Each row: days logged, average intake vs the
    average target over those same logged days (each day judged against the
    phase and day type in force *then*; targeted_days says how many logged
    days had a phase), protein vs target, the smoothed weight trend across
    the week, and training facts (sessions, cardio minutes, exercise kcal,
    strength volume). The measured-TDEE block rides along. Exercise kcal is
    a fact, never subtracted from anything — the measured TDEE already
    contains all activity. The numbers are facts; the judgment on them is
    yours, guided by profile_context.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await stats_domain.weekly_review(session, subject=who.subject, weeks=weeks)


@mcp.tool
async def get_tdee() -> dict[str, Any]:
    """The user's measured TDEE: what they actually burn per day, computed
    from logged intake against the smoothed weight trend over the last 21
    complete days — no formula guessing.

    tdee_kcal is null when the data cannot support an estimate; `reasons`
    says why, machine-readably (insufficient_logging / insufficient_weight_data
    / insufficient_history), and `coverage` shows the progress toward enough.
    A computable estimate may still be flagged confidence "low"
    (new_phase_water_shift, marginal_logging, sparse_weigh_ins) — show it
    with the caveat, don't hide it. `inputs` carries the arithmetic's
    ingredients so the number is auditable. Interpretation and coaching are
    yours; this is arithmetic.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await stats_domain.get_tdee(session, subject=who.subject)


@mcp.tool
async def training_history(exercise: str | None = None, weeks: int = 8) -> dict[str, Any]:
    """Training over the last ISO weeks (default 8, max 26), newest first:
    sessions, cardio minutes, exercise kcal, sets and strength volume per
    week.

    `exercises` lists the movement names that appear in the window, exactly
    as the user logs them ("penkki" stays "penkki"). Pass one back as
    `exercise` (matched case-insensitively) to also get that movement's
    progression: per-session top set and e5RM (Epley), the load trend.
    Unknown names error rather than guess — check `exercises` or ask.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await stats_domain.training_history(
            session, subject=who.subject, exercise=exercise, weeks=weeks
        )


@mcp.tool
async def weight_history(days: int = 30) -> dict[str, Any]:
    """The weight series, oldest first: raw daily points (weight, waist,
    notes), the 7-day smoothed trend, and the trailing 14-day rate in
    kg/week.

    The window is the last `days` calendar days (default 30, max 365), today
    included. This is also the read path before correcting a weigh-in:
    log_weight upserts on date, so read here what a day currently says. The
    smoothed series is the one to trend — the client may plot either.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await stats_domain.weight_history(session, subject=who.subject, days=days)


@mcp.tool
async def export_my_data() -> dict[str, Any]:
    """Everything this account owns, as one structured JSON dataset: profile,
    coaching-note history, every meal with its log-time snapshots, exercise
    sessions with sets, weights, goal phases, day-type marks, templates, own
    foods, and the movement catalog.

    This is the complete archive (GDPR data portability) and the migration
    path out — suitable for saving to a file or transforming for another
    service, not for answering day-to-day questions: the read tools
    (daily_summary, weekly_review, weight_history…) are the right size for
    those. `counts` states row counts per table. The same dataset is
    downloadable in the web UI as a zip of CSVs plus this JSON.
    """
    who = await _caller()
    async with SessionLocal() as session:
        return await export_domain.export_account(session, subject=who.subject)
