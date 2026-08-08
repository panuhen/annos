"""Caller identity — the single seam between Annos and Better Auth.

Better Auth (in the Next.js app) is the OAuth 2.1 authorization server. This API
is only a resource server. Two credential shapes reach us:

  * MCP clients present an opaque OAuth access token. Better Auth stores those
    in its `oauthAccessToken` table and exposes no RFC 7662 introspection
    endpoint; its own resource-server client validates by calling
    `/mcp/get-session`, so we do the same and cache the result briefly.
    (The discovery metadata advertises `/mcp/userinfo`, but better-auth 1.6
    never registers that endpoint — only the oidc-provider plugin has a
    userinfo, and we don't run it.)
  * The web UI presents a JWT minted by Better Auth's `jwt` plugin, verified
    offline against the JWKS at `{auth_base_url}/jwks` (EdDSA/Ed25519).

Telling them apart: a JWS has exactly two dots; Better Auth's opaque tokens
have none.

Identity always comes from the token, never from a tool parameter. Nothing here
reads Better Auth's tables: the API's database role has no access to them.

The `email` scope is never requested, and the JWT payload is pinned to standard
claims (definePayload in web/src/lib/auth.ts), so an address never reaches this
service even as a claim. The only thing we take from a credential is the
subject — the nickname is Annos' own data, in user_profile (see nickname.py).
"""

import time
from dataclasses import dataclass

import httpx
import jwt
import structlog

from annos.config import settings

log = structlog.get_logger(__name__)

# Better Auth's jwt plugin signs with EdDSA (Ed25519) by default. A fixed
# allowlist, not read from the token: the token does not get to pick how it is
# verified.
_JWT_ALGORITHMS = ["EdDSA"]

# Seconds of clock skew tolerated on exp/iat between us and the Next.js app.
_JWT_LEEWAY_SECONDS = 10


@dataclass(frozen=True)
class Caller:
    """A validated caller. `subject` is the Better Auth user id.

    Nothing else is carried: the nickname and every profile field belong to
    Annos' own user_profile row, keyed by this subject.
    """

    subject: str


class AuthError(Exception):
    """Raised when a credential is missing, malformed, or rejected upstream."""


# token -> (expires_at_monotonic, Caller)
_cache: dict[str, tuple[float, Caller]] = {}


def _cache_get(token: str) -> Caller | None:
    entry = _cache.get(token)
    if entry is None:
        return None
    expires_at, caller = entry
    if expires_at < time.monotonic():
        del _cache[token]
        return None
    return caller


def _cache_put(token: str, caller: Caller) -> None:
    _cache[token] = (time.monotonic() + settings.token_cache_ttl_seconds, caller)


# Rejected opaque tokens, token -> expires_at_monotonic. Only successes used to
# be cached, which meant every request with a garbage bearer token cost one
# outbound call to /mcp/get-session — a flood of unique invalid tokens became
# a request-for-request amplification against the Next.js app, which sits on
# the MCP critical path. A rejected token never becomes valid, so caching the
# rejection is safe. Bounded because the attacker controls the key space.
_NEGATIVE_CACHE_MAX = 10_000
_negative_cache: dict[str, float] = {}


def _negative_get(token: str) -> bool:
    expires_at = _negative_cache.get(token)
    if expires_at is None:
        return False
    if expires_at < time.monotonic():
        del _negative_cache[token]
        return False
    return True


def _negative_put(token: str) -> None:
    if len(_negative_cache) >= _NEGATIVE_CACHE_MAX:
        # Crude but bounded: a flood pays a full refill, we never grow past
        # the cap.
        _negative_cache.clear()
    _negative_cache[token] = time.monotonic() + settings.token_cache_ttl_seconds


async def _get_session(token: str) -> Caller:
    """Validate an opaque OAuth access token against Better Auth.

    `/mcp/get-session` answers 200 for every well-formed request and signals an
    invalid or expired token with a JSON `null` body, so the status code alone
    proves nothing.
    """
    url = f"{settings.auth_base_url.rstrip('/')}/mcp/get-session"
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    if response.status_code == 401:
        _negative_put(token)
        raise AuthError("token rejected by authorization server")
    if response.status_code >= 400:
        # Upstream trouble is not the caller's fault; surface it as such rather
        # than telling them their token is bad — and never cache it against the
        # token, or an outage would keep rejecting valid credentials after it.
        log.error("get_session_failed", status=response.status_code)
        raise AuthError(f"authorization server returned {response.status_code}")

    data = response.json()
    if data is None:
        _negative_put(token)
        raise AuthError("token rejected by authorization server")

    subject = data.get("userId")
    if not subject:
        _negative_put(token)
        raise AuthError("session response carried no subject")

    return Caller(subject=subject)


# (expires_at_monotonic, key set) — one authorization server, one key set.
_jwks_cache: tuple[float, jwt.PyJWKSet] | None = None


async def _jwks(*, force_refresh: bool = False) -> jwt.PyJWKSet:
    global _jwks_cache
    if not force_refresh and _jwks_cache is not None:
        expires_at, key_set = _jwks_cache
        if expires_at >= time.monotonic():
            return key_set

    url = f"{settings.auth_base_url.rstrip('/')}/jwks"
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url)

    if response.status_code >= 400:
        log.error("jwks_fetch_failed", status=response.status_code)
        raise AuthError(f"authorization server returned {response.status_code}")

    try:
        key_set = jwt.PyJWKSet.from_dict(response.json())
    except jwt.PyJWKSetError as exc:
        log.error("jwks_unusable", error=str(exc))
        raise AuthError("authorization server returned an unusable key set") from exc

    _jwks_cache = (time.monotonic() + settings.jwks_cache_ttl_seconds, key_set)
    return key_set


def _key_for(key_set: jwt.PyJWKSet, kid: str | None) -> jwt.PyJWK | None:
    for key in key_set.keys:
        if key.key_id == kid:
            return key
    return None


async def _verify_jwt(token: str) -> Caller:
    """Verify a web-UI JWT offline. No round trip except the cached JWKS."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise AuthError("malformed JWT") from exc

    key = _key_for(await _jwks(), header.get("kid"))
    if key is None:
        # Unknown kid usually means the signing key rotated under us; give the
        # authorization server one chance to say so before rejecting.
        key = _key_for(await _jwks(force_refresh=True), header.get("kid"))
    if key is None:
        raise AuthError("token signed with an unknown key")

    try:
        claims = jwt.decode(
            token,
            key=key.key,
            algorithms=_JWT_ALGORITHMS,
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
            leeway=_JWT_LEEWAY_SECONDS,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.InvalidTokenError as exc:
        raise AuthError("token rejected") from exc

    return Caller(subject=claims["sub"])


async def resolve_caller(authorization: str | None) -> Caller:
    """Resolve the caller from an Authorization header.

    Phase 0: when ANNOS_DEV_SUBJECT is set, token validation is skipped entirely.
    This must be unset in production.
    """
    if settings.dev_subject:
        return Caller(subject=settings.dev_subject)

    if not authorization:
        raise AuthError("missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("expected a Bearer token")

    cached = _cache_get(token)
    if cached is not None:
        return cached

    if token.count(".") == 2:
        # JWTs are verified offline; there is nothing upstream to protect,
        # so they skip the negative cache.
        caller = await _verify_jwt(token)
    else:
        if _negative_get(token):
            raise AuthError("token rejected by authorization server")
        caller = await _get_session(token)
    _cache_put(token, caller)
    return caller
