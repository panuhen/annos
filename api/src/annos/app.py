"""ASGI entrypoint: one FastAPI app serving both adapters.

/mcp   FastMCP over Streamable HTTP — what AI clients connect to
/api   REST — what the Next.js UI calls

Both are thin wrappers over annos.domain, which is where the logic lives.
"""

import logging

import structlog
from fastapi import FastAPI

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
