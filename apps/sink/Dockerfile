# syntax=docker/dockerfile:1
# Build context is the repository root (see infra/compose.yaml).
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Layer 1: only the manifests this app needs (explicit COPY: wildcards flatten paths)
COPY pyproject.toml uv.lock ./
COPY apps/sink/pyproject.toml apps/sink/pyproject.toml
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/db/pyproject.toml packages/db/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace --package newsdock-sink
# Layer 2: sources
COPY packages/core/src packages/core/src
COPY packages/db/src packages/db/src
COPY apps/sink/src apps/sink/src
RUN uv sync --frozen --no-dev --no-editable --package newsdock-sink

FROM python:3.12-slim
RUN useradd --create-home --uid 1000 app
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH
USER app
CMD ["python", "-m", "newsdock_sink"]
