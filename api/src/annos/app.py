"""ASGI entrypoint: one FastAPI app serving both adapters.

/mcp   FastMCP over Streamable HTTP — what AI clients connect to
/api   REST — what the Next.js UI calls

Both are thin wrappers over annos.domain, which is where the logic lives.
"""

import logging

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from annos.adapters.mcp import mcp
from annos.adapters.rest import router as rest_router
from annos.config import settings

# The logging counterpart of the email quarantine: only these keys reach the
# renderer, so a future `log.error("x", user=some_object)` drops the object
# instead of serialising PII into a log line. Widen deliberately, per field.
_LOG_FIELDS = {"event", "level", "timestamp", "status", "error"}


def _allowlist_fields(logger, method_name, event_dict):  # noqa: ANN001 — structlog processor signature
    return {key: value for key, value in event_dict.items() if key in _LOG_FIELDS}


structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _allowlist_fields,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelNamesMapping()[settings.log_level.upper()]
    ),
)

# ANNOS_DEV_SUBJECT disables all token validation (see identity.py) — fine on
# localhost, catastrophic anywhere real: every caller would silently become
# that one account. An https public origin means this is not local dev, so
# refuse to boot rather than run open.
if settings.dev_subject and settings.public_base_url.startswith("https://"):
    raise RuntimeError(
        "ANNOS_DEV_SUBJECT is set but ANNOS_PUBLIC_BASE_URL is https — "
        "refusing to start with token validation disabled outside local dev"
    )

# FastMCP's Streamable HTTP app owns a session manager that must be started and
# stopped with the process, so its lifespan has to be handed to FastAPI.
mcp_app = mcp.http_app(path="/")

app = FastAPI(
    title="Annos",
    version="0.1.0",
    lifespan=mcp_app.lifespan,
)

app.include_router(rest_router, prefix="/api")
app.mount("/mcp", mcp_app)


class McpPathNormalizer:
    """Serves /mcp and /mcp/ identically, without a redirect.

    The Streamable HTTP endpoint lives at /mcp/ (a mount), so the bare /mcp
    would otherwise answer 307. MCP clients don't reliably re-POST across
    redirects — Claude.ai normalises the connector URL to the no-slash form and
    then treats the redirect as "not a valid MCP server" — and behind the proxy
    the generated Location even downgrades to http://. Rewriting the ASGI scope
    in place makes the two spellings the same request; no Location header is
    ever produced.
    """

    def __init__(self, app):  # noqa: ANN001 — ASGI app, typed loosely on purpose
        self.app = app

    async def __call__(self, scope, receive, send):  # noqa: ANN001
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = dict(scope, path="/mcp/", raw_path=b"/mcp/")
        await self.app(scope, receive, send)


app.add_middleware(McpPathNormalizer)


# RFC 9728: the metadata for the resource {public_base_url}/mcp/ lives at
# /.well-known/oauth-protected-resource/mcp/ on the ORIGIN — the exact URL the
# 401's WWW-Authenticate advertises, not inside the /mcp mount where no client
# would look for it.
#
# Hand-rolled rather than the MCP SDK's create_protected_resource_routes: that
# helper types authorization_servers as list[AnyHttpUrl], and Pydantic
# normalises a bare authority by appending a slash — so the issuer would be
# advertised as https://annos.app/ while Better Auth's own
# oauth-authorization-server metadata, and every JWT `iss`, says
# https://annos.app. RFC 8414 requires the two byte-identical; a strict client
# (Claude.ai among them) rejects the authorization server on the slash mismatch
# and the MCP connect dies at "couldn't register". Emitting auth_jwt_issuer
# verbatim keeps them equal — the same string identity.py validates tokens
# against.
@app.get("/.well-known/oauth-protected-resource/mcp/", include_in_schema=False)
async def protected_resource_metadata() -> JSONResponse:
    return JSONResponse(
        {
            "resource": f"{settings.public_base_url}/mcp/",
            "authorization_servers": [settings.auth_jwt_issuer],
            "bearer_methods_supported": ["header"],
            "resource_name": "annos",
        }
    )


class Health(BaseModel):
    status: str


@app.get("/health")
async def health() -> Health:
    return Health(status="ok")
