# agent-platform — Design (Milestone 2, part 1)

Status: **approved** · 2026-10-14 · Spec: [spec.md](spec.md) · Detail (not required reading): [design-detail.md](design-detail.md)

**Reading order:** this file → `diagrams/index.html` (each diagram has a "Check" box) → ADR-0016, ADR-0017 in `../../adr/` → answer the checklist at the bottom.

## 1. Components (ids continue the numbering; unchanged components not listed)

| Id | Component | Change | Notes |
|---|---|---|---|
| C-11 | Auth middleware (API `adapters/auth.py`) | **new** | Pure ASGI, guards `/mcp*`: Bearer key → agent, 401 if unknown/revoked/disabled, then rate limit (429 + `Retry-After`). `auth_required=false` → anonymous agent (one shared rate bucket) |
| C-12 | Agent registry (`domain/agents.py` + `adapters/agents_repo.py`) | **new** | Pure key make/parse/hash/verify; SQL for agents, keys, cursors |
| C-13 | Rate limiter (`domain/ratelimit.py`) | **new** | Fixed one-minute window per agent id, injectable clock, in memory |
| C-14 | Admin routes (`/api/admin/*`) | **new** | Create/list/disable agents, issue/revoke keys; `Authorization: Bearer <NEWSDOCK_ADMIN_TOKEN>` |
| C-6 | API | **changed** | `submit_analysis` stores the authenticated name; `list_new_articles` uses the server cursor; new tool `ack_cursor` |
| C-5 | PostgreSQL | **changed** | New tables `agents`, `api_keys`, `agent_cursors` (migration 0004) |
| C-7 | Demo agent | **changed** | Sends `Authorization` header (key from `.env`), drops the cursor file, calls `ack_cursor` after a batch |

## 2. Key flows

- **F-8 Provision:** admin → C-14 create agent → key returned once → owner puts it in `.env`. (Sequence 1)
- **F-9 Authenticated run:** C-7 → C-11 (verify, rate limit) → `list_new_articles` (server cursor) → score → `submit_analysis` → `ack_cursor`. (Sequence 1)
- **F-10 Revoke:** admin revokes key/disables agent → next request 401 (no cache beyond the request). (State diagram 4)
- Web UI browse (F-3) unchanged: open `GET /api/*` (spec D-7).

## 3. Contracts (deltas)

| Table | Columns |
|---|---|
| `agents` | `id` uuid PK, `name` text UNIQUE, `status` (`active`\|`disabled`), `created_at` |
| `api_keys` | `id` uuid PK, `agent_id` FK→agents CASCADE, `prefix` text UNIQUE, `key_hash` text, `created_at`, `revoked_at` NULL, `last_used_at` NULL |
| `agent_cursors` | `agent_id` PK FK→agents CASCADE, `seq` bigint, `updated_at` |

Key format `ndk_<prefix>_<secret>`; only `prefix` + `sha256(secret)` stored.

| Surface | Auth |
|---|---|
| `/mcp*` (all tools) | agent key (or anonymous if `auth_required=false`) |
| `/api/admin/*` | admin token only; agent keys get 403 |
| `GET /api/articles*`, `/api/health` | open (spec D-7) |

Config (ADR-0013): `api.auth_required` (true), `api.rate_limit_per_minute` (600, 0 = off; was 120 until the live run, see plan T-08). Secret in `.env`: `NEWSDOCK_ADMIN_TOKEN`, agent `NEWSDOCK_AGENT_API_KEY`.

## 4. Tricky parts

- **Identity inside tools:** the middleware stores the verified agent on `scope["state"]`; tools read it from the MCP request (`ctx.request_context.request.state`). Stateful MCP sessions mean a contextvar would be unsafe, so state-on-request is the choice. Spike first (plan T-01); fallback: tools re-resolve from `ctx.headers`.
- **At-least-once cursor:** advance only on `ack_cursor`, forward-only (ADR-0017).
- **Name vs. identity:** `analyses.agent_name` = the agent's unique name; caller-supplied name is ignored for authenticated agents, accepted for anonymous (M1 compatibility).
- **Existing tests/compose:** default `auth_required=true` means every compose/infra scene must provision an agent key.

## 5. Failure modes (top)

| Failure | Result |
|---|---|
| Missing/unknown/revoked key | 401, no tool runs, no detail about which |
| Admin token unset | admin routes return 404; agents cannot be created (documented in README) |
| Rate limit exceeded | 429 + `Retry-After`; agent retries next loop |
| Crash between submit and ack | batch re-scored; analyses upsert |
| API restart | rate counters reset; cursors and keys persisted |

## 6. Technology

Existing stack only (FastAPI, SQLAlchemy 2, Alembic, `mcp`); stdlib `secrets`, `hashlib`, `hmac`. No new dependency. Rate limiter in memory is valid because `uvicorn_workers: 1` **[verified: newsdock.yaml]**.

## 7. AC coverage

| AC | Component / flow |
|---|---|
| AC-1, AC-2 | C-14, C-12 / F-8 |
| AC-3, AC-4, AC-5 | C-11, C-12 / F-9, F-10 |
| AC-6 | C-6, C-11 / F-9 |
| AC-7 | C-14 |
| AC-8, AC-9 | C-6, C-12 (`agent_cursors`) / F-9 |
| AC-10 | C-11 (`auth_required`) |
| AC-11 | C-13, C-11 |
| AC-12 | C-7 / F-9 end to end |

## Questions to answer before approving this design

- [x] Is a new MCP tool `ack_cursor` acceptable (changes the "fixed names" list), versus acking implicitly on the next `list_new_articles`? **Yes, MCP tool (2026-10-14).**
- [x] Should agents also be able to use the server cursor over REST, or MCP only for now? **MCP only (2026-10-14).**
- [x] Is leaving anonymous traffic un-rate-limited (when `auth_required=false`) fine? **No: anonymous traffic shares one rate bucket (2026-10-14).**
- [x] Is `sha256` of a 256-bit random secret acceptable instead of a slow password hash? **Yes (ADR-0016).**
- [x] Should unset `NEWSDOCK_ADMIN_TOKEN` disable admin routes (current) or fail the API start? **Disable (404).**
