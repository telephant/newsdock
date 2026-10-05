# syntax=docker/dockerfile:1
# Migration job image (not one of the six apps). Build context is the repository root.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/db/pyproject.toml packages/db/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace --package newsdock-db --extra migrate
COPY packages/db/src packages/db/src
RUN uv sync --frozen --no-dev --no-editable --package newsdock-db --extra migrate

FROM python:3.12-slim
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY infra/migrations /app/infra/migrations
ENV PATH=/app/.venv/bin:$PATH
USER app
CMD ["alembic", "-c", "infra/migrations/alembic.ini", "upgrade", "head"]
