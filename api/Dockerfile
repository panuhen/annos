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

# Migrate + grant on startup, then hand off to the server. The platform
# (Coolify) has no one-shot job step and forces restart on every service, so a
# separate migrate container would loop forever; folding it into startup is the
# proven pattern. alembic and apply_grants use the owner role
# (ANNOS_MIGRATION_DATABASE_URL); the server then connects as the restricted
# annos_api role (ANNOS_DATABASE_URL). `exec` makes uvicorn PID 1 for signals.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run python -m annos.apply_grants && exec uv run uvicorn annos.app:app --host 0.0.0.0 --port 8000"]
