FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
# Vendored seed data (the Compendium MET catalog) — small and static, and
# copying it in keeps `python -m annos.seed_activities` runnable in the
# container where the deploy has no repo checkout.
COPY data ./data
# grants.sql, applied by annos.apply_grants on startup (see below).
COPY db ./db

RUN uv sync

EXPOSE 8000

# Ensure-role + migrate + grant on startup, then hand off to the server. The
# platform (Coolify) has no one-shot job step and forces restart on every
# service, so a separate migrate container would loop forever; folding it into
# startup is the proven pattern. ensure_roles must run first: Coolify never
# delivers the ./db/init mount, so the annos_api role is otherwise never created
# and apply_grants dies with UndefinedObjectError. ensure_roles, alembic and
# apply_grants all use the owner role (ANNOS_MIGRATION_DATABASE_URL); the server
# then connects as the restricted annos_api role (ANNOS_DATABASE_URL). `exec`
# makes uvicorn PID 1 for signals.
# --forwarded-allow-ips '*': uvicorn only honours X-Forwarded-Proto from
# 127.0.0.1 by default, so behind Traefik every generated absolute URL (e.g. a
# redirect Location) downgraded to http://. The container port is only
# reachable over the compose network, so trusting all peers is safe here.
# --no-access-log: the default access line joins the real client IP (from
# X-Forwarded-For) with the full query string, and food/activity search carry
# health-adjacent free text in the query — so every request would log who asked
# what. Liveness has /health; structured app logs stay on (with a field
# allowlist, see app.py). This keeps IP and behaviour from meeting in a log.
CMD ["sh", "-c", "uv run python -m annos.ensure_roles && uv run alembic upgrade head && uv run python -m annos.apply_grants && exec uv run uvicorn annos.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' --no-access-log"]
