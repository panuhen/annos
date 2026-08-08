"""ASGI entrypoint: one FastAPI app serving both adapters.

/mcp   FastMCP over Streamable HTTP — what AI clients connect to
/api   REST — what the Next.js UI calls

Both are thin wrappers over annos.domain, which is where the logic lives.
"""

import logging

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from annos.adapters.mcp import mcp
from annos.adapters.rest import router as rest_router
from annos.config import settings

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelNamesMapping()[settings.log_level.upper()]
    ),
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
