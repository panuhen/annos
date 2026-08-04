"""The identity seam: bearer token in, subject out, nothing else.

This is the path that had never executed — ANNOS_DEV_SUBJECT short-circuits it
in every manual run — so it is tested here against a mocked authorization
server. What is *not* covered: whether Better Auth's real /oauth2/userinfo
answers in this shape. That needs the Next.js app.
"""

import dataclasses

import httpx
import pytest
from fastmcp.server.http import set_http_request
from starlette.requests import Request

from annos import identity
from annos.adapters import mcp as mcp_adapter
from annos.config import settings


@pytest.fixture(autouse=True)
def production_like(monkeypatch):
    """Turn off the Phase 0 bypass, and start from a cold token cache."""
    monkeypatch.setattr(settings, "dev_subject", None)
    identity._cache.clear()
    yield
    identity._cache.clear()


def mock_authorization_server(monkeypatch, handler):
    class _Client(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(identity.httpx, "AsyncClient", _Client)


def responds(payload: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

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


async def test_valid_token_resolves_to_its_subject(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"sub": "user-abc"})

    mock_authorization_server(monkeypatch, handler)

    caller = await identity.resolve_caller("Bearer tok-123")

    assert caller == identity.Caller(subject="user-abc")
    assert seen["url"].endswith("/oauth2/userinfo")
    assert seen["authorization"] == "Bearer tok-123"


async def test_only_the_subject_is_kept(monkeypatch):
    """The `email` scope is never requested, but if an address turns up in the
    response anyway it must not enter the process. Caller carries one field."""
    mock_authorization_server(monkeypatch, responds({"sub": "user-abc", "email": "a@example.com"}))

    caller = await identity.resolve_caller("Bearer tok-123")

    assert [field.name for field in dataclasses.fields(caller)] == ["subject"]


async def test_rejected_token_is_an_auth_error(monkeypatch):
    mock_authorization_server(monkeypatch, responds({}, status=401))

    with pytest.raises(identity.AuthError, match="rejected"):
        await identity.resolve_caller("Bearer tok-123")


async def test_upstream_failure_is_not_blamed_on_the_caller(monkeypatch):
    """A 503 from Better Auth is not a bad token; say so, or every outage looks
    like a login problem."""
    mock_authorization_server(monkeypatch, responds({}, status=503))

    with pytest.raises(identity.AuthError, match="503"):
        await identity.resolve_caller("Bearer tok-123")


async def test_response_without_a_subject_is_rejected(monkeypatch):
    mock_authorization_server(monkeypatch, responds({"nickname": "someone"}))

    with pytest.raises(identity.AuthError, match="subject"):
        await identity.resolve_caller("Bearer tok-123")


async def test_a_validated_token_is_cached(monkeypatch):
    """Next.js is on the MCP critical path; every tool call must not become a
    round trip to it."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"sub": "user-abc"})

    mock_authorization_server(monkeypatch, handler)

    await identity.resolve_caller("Bearer tok-123")
    await identity.resolve_caller("Bearer tok-123")

    assert len(calls) == 1


async def test_the_cache_expires(monkeypatch):
    """A revoked token must stop working, so the entry is short-lived."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"sub": "user-abc"})

    mock_authorization_server(monkeypatch, handler)
    monkeypatch.setattr(settings, "token_cache_ttl_seconds", -1)

    await identity.resolve_caller("Bearer tok-123")
    await identity.resolve_caller("Bearer tok-123")

    assert len(calls) == 2


async def test_the_cache_is_keyed_by_token(monkeypatch):
    """Two users, two tokens: the second must not inherit the first's subject."""
    subjects = iter(["user-abc", "user-xyz"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sub": next(subjects)})

    mock_authorization_server(monkeypatch, handler)

    first = await identity.resolve_caller("Bearer tok-one")
    second = await identity.resolve_caller("Bearer tok-two")

    assert (first.subject, second.subject) == ("user-abc", "user-xyz")


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
        return httpx.Response(200, json={"sub": "user-abc"})

    mock_authorization_server(monkeypatch, handler)

    with set_http_request(http_request({"authorization": "Bearer tok-123"})):
        caller = await mcp_adapter._caller()

    assert caller.subject == "user-abc"
    assert seen["authorization"] == "Bearer tok-123"


async def test_mcp_without_a_token_is_rejected():
    with set_http_request(http_request({})), pytest.raises(identity.AuthError):
        await mcp_adapter._caller()
