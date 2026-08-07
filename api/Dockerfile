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

RUN uv sync

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "annos.app:app", "--host", "0.0.0.0", "--port", "8000"]
