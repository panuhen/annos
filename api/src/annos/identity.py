"""Caller identity — the single seam between Annos and Better Auth.

Better Auth (in the Next.js app) is the OAuth 2.1 authorization server. This API
is only a resource server. Two credential shapes reach us:

  * MCP clients present an opaque OAuth access token. Better Auth stores those in
    its `oauthAccessToken` table and exposes no RFC 7662 introspection endpoint,
    so we validate by calling `/oauth2/userinfo` and cache the result briefly.
  * The web UI presents a JWT minted by Better Auth's `jwt` plugin, which we can
    verify offline against the JWKS at `/api/auth/jwks`. Not yet implemented —
    see the TODO below.

Identity always comes from the token, never from a tool parameter. Nothing here
reads Better Auth's tables: the API's database role has no access to them.

We deliberately do not request the `email` scope, so an address never reaches
this service even as a claim. The only thing we take from a token is the subject —
the nickname is Annos' own data, in user_profile (see nickname.py).
"""

import time
from dataclasses import dataclass

import httpx
import structlog

from annos.config import settings

log = structlog.get_logger(__name__)


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


async def _userinfo(token: str) -> Caller:
    """Validate an opaque OAuth access token against Better Auth."""
    url = f"{settings.auth_base_url.rstrip('/')}/oauth2/userinfo"
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    if response.status_code == 401:
        raise AuthError("token rejected by authorization server")
    if response.status_code >= 400:
        # Upstream trouble is not the caller's fault; surface it as such rather
        # than telling them their token is bad.
        log.error("userinfo_failed", status=response.status_code)
        raise AuthError(f"authorization server returned {response.status_code}")

    subject = response.json().get("sub")
    if not subject:
        raise AuthError("userinfo response carried no subject")

    return Caller(subject=subject)


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

    # TODO(auth): branch here once the web UI path lands. A Better Auth `jwt`
    # plugin token is a JWS and can be verified offline against
    # {auth_base_url}/jwks (EdDSA/Ed25519 by default), avoiding this round trip.
    # Opaque OAuth tokens have no dots; JWTs have exactly two.
    caller = await _userinfo(token)
    _cache_put(token, caller)
    return caller
