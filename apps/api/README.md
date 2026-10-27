# newsdock-api

Python app, component C-6. Milestone M0 provides the skeleton only; the behaviour below arrives in M1 (see `docs/specs/mvp/design.md`).

## Purpose

FastAPI service that serves the MCP server (streamable HTTP, `/mcp`) and the REST API (`/api/*`) over one service layer. The only reader of the article store for agents and the UI.

## Entrypoint

`python -m newsdock_api` runs `src/newsdock_api/__main__.py`, which loads `Settings` from `config.py` and starts the app. In M0 it prints its name and exits 0.

Accounts (M2 `ui-login`, ADR-0020/0021): `domain/accounts.py` (roles, permission table, password and email policy, session rules), `domain/loginlimit.py` (per-account login throttle), `adapters/principal.py` (one resolver for agent key, admin token and session cookie, plus the route guards and the Origin and JSON write checks), `adapters/accounts_api.py` (`/api/auth/*`, `/api/users*`, `/api/admin/users/reset-password`), `adapters/users_repo.py` (users and sessions, advisory locks for the first and the last owner), `adapters/passwords.py` (argon2id), `adapters/live.py` (`GET /api/live`) on the shared stream loop `adapters/streaming.py`. Settings: `auth_*`, `cors_*`, `live_max_streams_per_user` in `infra/config/newsdock.yaml`.

Layout (rules DR-1 to DR-9 in `docs/specs/foundation/spec.md`): `domain/` is pure logic, `adapters/` holds all I/O, `config.py` is the only place environment variables are read.

## Dependencies

Today: `newsdock-core` (shared package) and `pydantic-settings`. Planned for M1: `fastapi`, the `mcp` SDK and `newsdock-db`.

## Run/Test

```bash
make test APP=api                      # unit tests
uv run python -m newsdock_api          # run the entrypoint
make build APP=api                     # build the image newsdock-api:dev
```
