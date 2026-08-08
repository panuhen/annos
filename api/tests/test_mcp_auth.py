"""The OAuth discovery handshake on the MCP surface.

The in-memory transport used everywhere else never touches HTTP, which is
precisely where the last auth bug hid. These tests go through the real ASGI
app: a request without a valid token must get HTTP 401 with a WWW-Authenticate
header naming the protected-resource metadata, and that metadata must name
Better Auth — this is how a remote MCP client finds the login page at all.
"""

import httpx
import pytest

from annos import identity
from annos.app import app
from annos.config import settings

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "probe", "version": "0"},
    },
}

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


@pytest.fixture(autouse=True)
def production_like(monkeypatch):
    monkeypatch.setattr(settings, "dev_subject", None)
    identity._cache.clear()
    yield
    identity._cache.clear()


def mock_authorization_server(monkeypatch, handler):
    class _Client(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(identity.httpx, "AsyncClient", _Client)


@pytest.fixture
async def http():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def test_no_token_gets_401_with_discovery_pointer(http):
    response = await http.post("/mcp/", json=INITIALIZE, headers=MCP_HEADERS)

    assert response.status_code == 401
    challenge = response.headers.get("www-authenticate", "")
    assert challenge.startswith("Bearer")
    assert f"{settings.public_base_url}/.well-known/oauth-protected-resource/mcp/" in challenge


async def test_the_bare_mcp_path_serves_instead_of_redirecting(http):
    """Claude.ai normalises the connector URL to /mcp without the slash and
    treats the mount's 307 as "not a valid MCP server" — the two spellings must
    be the same request, with no Location round-trip."""
    response = await http.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS)

    assert response.status_code == 401
    assert "location" not in response.headers
    challenge = response.headers.get("www-authenticate", "")
    assert challenge.startswith("Bearer")


async def test_a_rejected_token_gets_401_not_a_tool_error(http, monkeypatch):
    """Before this layer existed, a bad token produced a JSON-RPC tool error
    over HTTP 200 — and a remote client had nothing to hang discovery on."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="null", headers={"content-type": "application/json"})

    mock_authorization_server(monkeypatch, handler)

    response = await http.post(
        "/mcp/",
        json=INITIALIZE,
        headers={**MCP_HEADERS, "Authorization": "Bearer garbage"},
    )

    assert response.status_code == 401
    assert "www-authenticate" in response.headers


async def test_the_metadata_names_better_auth(http):
    """RFC 9728, served at the origin-level well-known path — not inside the
    /mcp mount, where no client would look for it."""
    response = await http.get("/.well-known/oauth-protected-resource/mcp/")

    assert response.status_code == 200
    metadata = response.json()
    assert metadata["resource"] == f"{settings.public_base_url}/mcp/"
    # Byte-exact, no rstrip: the advertised authorization server must match
    # Better Auth's oauth-authorization-server `issuer` and every JWT `iss`
    # character for character, or a strict MCP client (Claude.ai) rejects the
    # server at discovery. A trailing slash here is the bug this guards.
    assert metadata["authorization_servers"] == [settings.auth_jwt_issuer]


async def test_a_valid_token_reaches_the_server(http, monkeypatch):
    """The gate must open too: with a token Better Auth vouches for, the
    request passes the middleware and MCP initialize actually answers."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/mcp/get-session")
        return httpx.Response(200, json={"userId": "user-abc"})

    mock_authorization_server(monkeypatch, handler)

    # The session manager only runs inside the app's lifespan; ASGITransport
    # does not start it, so enter it by hand.
    async with app.router.lifespan_context(app):
        response = await http.post(
            "/mcp/",
            json=INITIALIZE,
            headers={**MCP_HEADERS, "Authorization": "Bearer tok-opaque"},
        )

    assert response.status_code == 200
    assert "annos" in response.text  # serverInfo from a real initialize result
