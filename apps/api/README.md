# newsdock-api

Python app, component C-6. Milestone M0 provides the skeleton only; the behaviour below arrives in M1 (see `docs/specs/mvp/design.md`).

## Purpose

FastAPI service that serves the MCP server (streamable HTTP, `/mcp`) and the REST API (`/api/*`) over one service layer. The only reader of the article store for agents and the UI.

## Entrypoint

`python -m newsdock_api` runs `src/newsdock_api/__main__.py`, which loads `Settings` from `config.py` and starts the app. In M0 it prints its name and exits 0.

Layout (rules DR-1 to DR-9 in `docs/specs/foundation/spec.md`): `domain/` is pure logic, `adapters/` holds all I/O, `config.py` is the only place environment variables are read.

## Dependencies

Today: `newsdock-core` (shared package) and `pydantic-settings`. Planned for M1: `fastapi`, the `mcp` SDK and `newsdock-db`.

## Run/Test

```bash
make test APP=api                      # unit tests
uv run python -m newsdock_api          # run the entrypoint
make build APP=api                     # build the image newsdock-api:dev
```

<!-- ci path-filter test: touches only apps/api/README.md -->
