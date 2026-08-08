"""The identity seam: bearer token in, subject out, nothing else.

This is the path that had never executed — ANNOS_DEV_SUBJECT short-circuits it
in every manual run — so it is tested here against a mocked authorization
server. Two credential shapes: opaque OAuth access tokens are validated against
Better Auth's /mcp/get-session (what its own resource-server client calls);
web-UI JWTs are verified offline against the JWKS.
"""

import dataclasses
import json
import time

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastmcp.server.http import set_http_request
from starlette.requests import Request

from annos import identity
from annos.adapters import mcp as mcp_adapter
from annos.config import settings


@pytest.fixture(autouse=True)
def production_like(monkeypatch):
    """Turn off the Phase 0 bypass, and start from cold caches."""
    monkeypatch.setattr(settings, "dev_subject", None)
    identity._cache.clear()
    identity._negative_cache.clear()
    identity._jwks_cache = None
    yield
    identity._cache.clear()
    identity._negative_cache.clear()
    identity._jwks_cache = None


def mock_authorization_server(monkeypatch, handler):
    class _Client(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(identity.httpx, "AsyncClient", _Client)


def responds(payload, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        # httpx treats json=None as "no body", but Better Auth answers an
        # invalid token with a literal JSON null — build that by hand.
        return httpx.Response(
            status, content=json.dumps(payload), headers={"content-type": "application/json"}
        )

    return handler


async def test_dev_subject_bypasses_validation(monkeypatch):
    """Phase 0 only, and the reason the real path below had never run."""
    monkeypatch.setattr(settings, "dev_subject", "dev-subject-0001")

    assert await identity.resolve_caller(None) == identity.Caller(subject="dev-subject-0001")


async def test_missing_header_is_rejected():
    with pytest.raises(identity.AuthError):
        await identity.resolve_caller(None)


@pytest.mark.parametrize("header", ["Basic abc123", "Bearer", "Bearer ", "abc123"])
async def test_malformed_credentials_are_rejected(header):
    with pytest.raises(identity.AuthError):
        await identity.resolve_caller(header)


# --- opaque OAuth access tokens (MCP clients) --------------------------------


async def test_valid_token_resolves_to_its_subject(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"userId": "user-abc", "scopes": "openid"})

    mock_authorization_server(monkeypatch, handler)

    caller = await identity.resolve_caller("Bearer tok-123")

    assert caller == identity.Caller(subject="user-abc")
    assert seen["url"].endswith("/mcp/get-session")
    assert seen["authorization"] == "Bearer tok-123"


async def test_only_the_subject_is_kept(monkeypatch):
    """The `email` scope is never requested, but if an address turns up in the
    response anyway it must not enter the process. Caller carries one field."""
    mock_authorization_server(
        monkeypatch, responds({"userId": "user-abc", "email": "a@example.com"})
    )

    caller = await identity.resolve_caller("Bearer tok-123")

    assert [field.name for field in dataclasses.fields(caller)] == ["subject"]


async def test_rejected_token_is_an_auth_error(monkeypatch):
    """Better Auth signals a bad or expired token as 200 with a JSON null body,
    not as a 401. The status code alone proves nothing."""
    mock_authorization_server(monkeypatch, responds(None))

    with pytest.raises(identity.AuthError, match="rejected"):
        await identity.resolve_caller("Bearer tok-123")


async def test_a_rejected_token_is_negatively_cached(monkeypatch):
    """A garbage bearer token must cost at most one upstream call. Without the
    negative cache, a flood of unique invalid tokens is amplified request-for-
    request into /mcp/get-session — an attack on the identity provider, which is
    on the MCP critical path."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=json.dumps(None))

    mock_authorization_server(monkeypatch, handler)

    for _ in range(3):
        with pytest.raises(identity.AuthError, match="rejected"):
            await identity.resolve_caller("Bearer tok-garbage")

    assert len(calls) == 1


async def test_the_negative_cache_expires(monkeypatch):
    """A rejection cached forever would outlive a token that later becomes
    valid — impossible for opaque tokens today, but the TTL keeps the negative
    cache from being a correctness trap if that ever changes."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=json.dumps(None))

    mock_authorization_server(monkeypatch, handler)
    monkeypatch.setattr(settings, "token_cache_ttl_seconds", -1)

    for _ in range(2):
        with pytest.raises(identity.AuthError):
            await identity.resolve_caller("Bearer tok-garbage")

    assert len(calls) == 2


async def test_upstream_failure_is_not_negatively_cached(monkeypatch):
    """A 503 is the server's problem, not the token's. Caching it would keep
    rejecting a valid credential after the outage cleared."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503, content=json.dumps({}))

    mock_authorization_server(monkeypatch, handler)

    for _ in range(2):
        with pytest.raises(identity.AuthError, match="503"):
            await identity.resolve_caller("Bearer tok-123")

    assert len(calls) == 2


async def test_upstream_failure_is_not_blamed_on_the_caller(monkeypatch):
    """A 503 from Better Auth is not a bad token; say so, or every outage looks
    like a login problem."""
    mock_authorization_server(monkeypatch, responds({}, status=503))

    with pytest.raises(identity.AuthError, match="503"):
        await identity.resolve_caller("Bearer tok-123")


async def test_response_without_a_subject_is_rejected(monkeypatch):
    mock_authorization_server(monkeypatch, responds({"scopes": "openid"}))

    with pytest.raises(identity.AuthError, match="subject"):
        await identity.resolve_caller("Bearer tok-123")


async def test_a_validated_token_is_cached(monkeypatch):
    """Next.js is on the MCP critical path; every tool call must not become a
    round trip to it."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"userId": "user-abc"})

    mock_authorization_server(monkeypatch, handler)

    await identity.resolve_caller("Bearer tok-123")
    await identity.resolve_caller("Bearer tok-123")

    assert len(calls) == 1


async def test_the_cache_expires(monkeypatch):
    """A revoked token must stop working, so the entry is short-lived."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"userId": "user-abc"})

    mock_authorization_server(monkeypatch, handler)
    monkeypatch.setattr(settings, "token_cache_ttl_seconds", -1)

    await identity.resolve_caller("Bearer tok-123")
    await identity.resolve_caller("Bearer tok-123")

    assert len(calls) == 2


async def test_the_cache_is_keyed_by_token(monkeypatch):
    """Two users, two tokens: the second must not inherit the first's subject."""
    subjects = iter(["user-abc", "user-xyz"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"userId": next(subjects)})

    mock_authorization_server(monkeypatch, handler)

    first = await identity.resolve_caller("Bearer tok-one")
    second = await identity.resolve_caller("Bearer tok-two")

    assert (first.subject, second.subject) == ("user-abc", "user-xyz")


# --- web-UI JWTs, verified offline against the JWKS --------------------------


def make_keypair(kid: str = "key-1"):
    private_key = Ed25519PrivateKey.generate()
    jwk = json.loads(pyjwt.algorithms.OKPAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk["alg"] = "EdDSA"
    return private_key, {"keys": [jwk]}


def mint(private_key, kid: str = "key-1", **overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": "user-jwt",
        "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience,
        "iat": now,
        "exp": now + 900,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return pyjwt.encode(claims, private_key, algorithm="EdDSA", headers={"kid": kid})


def serves_jwks(monkeypatch, jwks: dict):
    """Mock an authorization server that only answers the JWKS endpoint —
    offline verification must never hit anything else."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert str(request.url).endswith("/jwks"), f"unexpected round trip: {request.url}"
        return httpx.Response(200, json=jwks)

    mock_authorization_server(monkeypatch, handler)
    return calls


async def test_a_web_ui_jwt_verifies_offline(monkeypatch):
    private_key, jwks = make_keypair()
    calls = serves_jwks(monkeypatch, jwks)

    caller = await identity.resolve_caller(f"Bearer {mint(private_key)}")

    assert caller == identity.Caller(subject="user-jwt")
    assert len(calls) == 1  # the JWKS, nothing else


async def test_the_jwks_is_cached_across_tokens(monkeypatch):
    private_key, jwks = make_keypair()
    calls = serves_jwks(monkeypatch, jwks)

    await identity.resolve_caller(f"Bearer {mint(private_key)}")
    await identity.resolve_caller(f"Bearer {mint(private_key, sub='someone-else')}")

    assert len(calls) == 1


async def test_an_expired_jwt_is_rejected(monkeypatch):
    private_key, jwks = make_keypair()
    serves_jwks(monkeypatch, jwks)
    stale = mint(private_key, exp=int(time.time()) - 3600)

    with pytest.raises(identity.AuthError, match="rejected"):
        await identity.resolve_caller(f"Bearer {stale}")


async def test_a_jwt_from_the_wrong_issuer_is_rejected(monkeypatch):
    """Same key, wrong `iss` — a token minted for some other deployment must
    not work here just because the signature checks out."""
    private_key, jwks = make_keypair()
    serves_jwks(monkeypatch, jwks)
    foreign = mint(private_key, iss="http://evil.example")

    with pytest.raises(identity.AuthError, match="rejected"):
        await identity.resolve_caller(f"Bearer {foreign}")


async def test_a_jwt_for_another_audience_is_rejected(monkeypatch):
    private_key, jwks = make_keypair()
    serves_jwks(monkeypatch, jwks)
    foreign = mint(private_key, aud="http://other.example")

    with pytest.raises(identity.AuthError, match="rejected"):
        await identity.resolve_caller(f"Bearer {foreign}")


async def test_a_jwt_without_a_subject_is_rejected(monkeypatch):
    private_key, jwks = make_keypair()
    serves_jwks(monkeypatch, jwks)
    anonymous = mint(private_key, sub=None)

    with pytest.raises(identity.AuthError, match="rejected"):
        await identity.resolve_caller(f"Bearer {anonymous}")


async def test_a_forged_signature_is_rejected(monkeypatch):
    """Signed by a key the authorization server never published."""
    _, jwks = make_keypair()
    serves_jwks(monkeypatch, jwks)
    other_key, _ = make_keypair()

    with pytest.raises(identity.AuthError, match="rejected"):
        await identity.resolve_caller(f"Bearer {mint(other_key)}")


async def test_key_rotation_refetches_the_jwks_once(monkeypatch):
    """A kid we don't know usually means the key rotated: ask the server again
    before rejecting, but only once — an attacker's random kid must not turn
    every request into a JWKS fetch."""
    old_key, old_jwks = make_keypair(kid="old")
    new_key, new_jwks = make_keypair(kid="new")
    served = iter([old_jwks, new_jwks])
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=next(served))

    mock_authorization_server(monkeypatch, handler)

    await identity.resolve_caller(f"Bearer {mint(old_key, kid='old')}")
    caller = await identity.resolve_caller(f"Bearer {mint(new_key, kid='new')}")

    assert caller.subject == "user-jwt"
    assert len(calls) == 2


async def test_a_kid_the_server_does_not_know_is_rejected(monkeypatch):
    private_key, jwks = make_keypair(kid="key-1")
    serves_jwks(monkeypatch, jwks)

    with pytest.raises(identity.AuthError, match="unknown key"):
        await identity.resolve_caller(f"Bearer {mint(private_key, kid='mystery')}")


async def test_jwks_outage_is_not_blamed_on_the_caller(monkeypatch):
    private_key, _ = make_keypair()
    mock_authorization_server(monkeypatch, responds({}, status=503))

    with pytest.raises(identity.AuthError, match="503"):
        await identity.resolve_caller(f"Bearer {mint(private_key)}")


async def test_something_with_two_dots_that_is_not_a_jwt(monkeypatch):
    """Must fail as a bad credential, not as an unhandled parse error — and
    must not fall through to the opaque-token path."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no round trip expected for garbage")

    mock_authorization_server(monkeypatch, handler)

    with pytest.raises(identity.AuthError, match="malformed"):
        await identity.resolve_caller("Bearer not.a.jwt")


# --- how the token reaches the seam -----------------------------------------


def http_request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        }
    )


async def test_mcp_reads_the_bearer_token_off_the_request(monkeypatch):
    """Regression. FastMCP's get_http_headers() drops `authorization` from its
    default result — reasonable for a proxy forwarding headers onwards, fatal
    here, where that header is the only identity we get. The adapter has to ask
    for it explicitly, or every MCP call arrives anonymous."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"userId": "user-abc"})

    mock_authorization_server(monkeypatch, handler)

    with set_http_request(http_request({"authorization": "Bearer tok-123"})):
        caller = await mcp_adapter._caller()

    assert caller.subject == "user-abc"
    assert seen["authorization"] == "Bearer tok-123"


async def test_mcp_without_a_token_is_rejected():
    with set_http_request(http_request({})), pytest.raises(identity.AuthError):
        await mcp_adapter._caller()
