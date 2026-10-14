# agent-platform — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation (2026-10-14)

| # | Check | Method | Result |
|---|---|---|---|
| 1 | AC → test coverage | grep AC column of tests.md | **pass**: AC-1…AC-12 each ≥ 1 TC (18 TCs; TC-18 is the T-01 spike, TC-14 manual) |
| 2 | AC → design / task coverage | grep design.md §7; `Implements:` in tasks/ | **pass**: 12/12 both |
| 3 | Cross-doc names | `ack_cursor`, `auth_required`, `rate_limit_per_minute`, `NEWSDOCK_ADMIN_TOKEN`, `NEWSDOCK_AGENT_API_KEY`, `agent_cursors` consistent across spec/design/tests/tasks | **pass** |
| 4 | Proposed ADRs treated as decided | ADR-0016, ADR-0017 | **pass**: both Accepted 2026-10-14 |
| 5 | Untagged claims / invented numbers | 120 req/min and key length are provisional targets (spec §6, tests Measurements) | **pass** |
| 6 | Scope leaks from backlog.md | filters, push, UI login, rotation, scopes only under "Out of scope" | **pass** |
| 7 | Open questions / checklist items | grep `- [ ]` in spec/design | **pass**: none |

Open risk carried: the T-01 spike may change the identity mechanism (fallback documented in design.md §4). Existing M1 API/compose tests must be adapted to keys (T-05, T-08).

**Verdict: GO.** `gates.plan: approved`. No design-review.md exists, so nothing to retire.

## Spike first

**T-01** de-risks the two unverified claims the whole design rests on: (1) a pure-ASGI middleware on the outer app can hand the verified agent to MCP tool handlers (`ctx.request_context.request.state`), under stateful streamable-HTTP sessions; (2) the agent's MCP client can send an `Authorization` header (`Client(url)` takes none). If either fails, the fallbacks are in design.md §4 (`ctx.headers` re-resolve; explicit httpx transport).

## Phases and milestones

| Phase | Tasks | Milestone (ACs) | Effort |
|---|---|---|---|
| 0 Spike | T-01 | claims verified | 0.5 d |
| 1 Core | T-02, T-03 | key rules, limiter, tables, registry repo (AC-2) | 1 d |
| 2 Admin + auth | T-04, T-05 | AC-1, AC-3…AC-7, AC-10, AC-11 | 1.5 d |
| 3 Cursor | T-06 | AC-8, AC-9 | 0.5 d |
| 4 Agent + infra | T-07, T-08 | AC-12 end to end, docs | 1 d |

## Definition of Done (every task)

Tests first and red→green; `make check` green (plus `make test APP=<app>`; `make test-infra SCENE=…` where a task names it); `make config-python` green when a setting is added; docs/ADR updated in the same edit; no secrets in files, logs or YAML.

## Tasks

| Task | Title | Implements | Depends on |
|---|---|---|---|
| T-01 | Spike: identity through middleware + client header | AC-3, AC-4 (risk) | none |
| T-02 | Domain: keys, limiter, agent value types | AC-2, AC-11 | T-01 |
| T-03 | Tables, migration 0004, registry repo | AC-2, AC-5 | T-02 |
| T-04 | Settings + admin routes | AC-1, AC-7, AC-10 | T-03 |
| T-05 | Auth + rate-limit middleware, tool identity | AC-3…AC-6, AC-10, AC-11 | T-04 |
| T-06 | Server cursor and `ack_cursor` | AC-8, AC-9 | T-05 |
| T-07 | Demo agent: key header, ack, drop cursor file | AC-12 | T-06 |
| T-08 | Infra, provisioning, docs, live check | AC-12 | T-07 |

## Progress

T-01 ✅ 2026-10-14 — spike on `mcp` 2.3.0 (throwaway script, scratchpad, not committed), both claims **verified**:
1. A pure-ASGI middleware added with `app.add_middleware` on the outer FastAPI app (MCP mounted at `/`) that sets `scope["state"]["agent"]` is readable in a tool as `ctx.request_context.request.state.agent`; two calls in one session returned the right agent for each of two keys, and `ctx.headers["authorization"]` also works (fallback). Tool needs return type `dict[str, Any]` for structured output. No contextvar needed.
2. The client sends a Bearer header via `Client(streamable_http_client(url, http_client=httpx2.AsyncClient(headers={"Authorization": f"Bearer {key}"})))`. `Client(url)` takes no headers; the transport is passed as the context manager itself (not entered).
3. Side finding for T-07: a 401 surfaces on the client as an `ExceptionGroup` wrapping the HTTP error, so the agent must unwrap it to log a clear "unauthorized" message.

T-02 ✅ 2026-10-14 — `domain/agents.py` (Agent, ANONYMOUS, make_key/parse_key/hash_secret/verify; hex prefix 8 chars + secret 64 hex = 256 bits) and `domain/ratelimit.py` (fixed 60 s window, injectable clock, `limit=0` off, `ANONYMOUS_BUCKET`, prunes on rollover). TC-3 and TC-12 green (47 API unit tests), ruff, mypy, import-linter, web tests green. `make check` stops at `check_layout` DR-1 only because the loop harness writes `.claude/scheduled_tasks.lock` at the repo root (not from this task); remove the file when the loop ends, or allow `.claude` in `check_layout.py`.

T-03 ✅ 2026-10-14 — models `Agent`/`ApiKey`/`AgentCursor` (uuid ids via `gen_random_uuid()`), Alembic `0004_agents` (forward-only, `api_rw` SELECT/INSERT/UPDATE), `adapters/agents_repo.py` (`SqlAgentsRepo`: create_agent/add_key/revoke_key/set_status/list_agents/find_key/touch_key throttled to 1/min/get_cursor/advance_cursor with `GREATEST`), domain records `RegisteredAgent`, `StoredKey`, `KeySummary`, `AgentSummary`. TC-2 plus 7 more repo tests green (`pytest -m docker`), `make test-infra SCENE=db` green (autogenerate no-op holds), ruff/mypy/import-linter green. Only `make check` blocker is still the loop's `.claude/` lock (DR-1).

T-04 ✅ 2026-10-14 — settings `auth_required` (true), `rate_limit_per_minute` (120), `admin_token` (SecretStr, env `NEWSDOCK_ADMIN_TOKEN` only; empty in `.env.example`; the two non-secret keys listed in `newsdock.yaml`); `adapters/admin.py` router (`POST/GET /api/admin/agents`, `POST /agents/{id}/keys`, `DELETE /agents/{id}/keys/{key_id}`, `POST /agents/{id}/disable|enable`); `create_app(settings, agents_repo)` takes an injectable registry (`AgentRegistry` protocol in the domain). Admin auth: unset token → 404, missing/wrong → 401, well-formed agent key → 403. TC-1, TC-8 and the config part of TC-11 green as unit tests over an in-memory registry (the SQL path is covered by T-03's TC-2); `make config-python`, ruff, mypy green. Only `make check` blocker: the loop's `.claude/` lock (DR-1).

T-05 ✅ 2026-10-14 — `domain.agents.authenticate` (header → agent, pure) and `adapters/auth.py` `AuthMiddleware` (pure ASGI, wraps the app so it guards `/mcp*`): 401 + `WWW-Authenticate: Bearer` for missing/malformed/unknown/revoked/disabled, auth before limit, 429 + `Retry-After`, 503 on DB errors, `touch_key` per request (SQL-throttled to 1/min), agent on `scope["state"]`; anonymous when `auth_required=false` (a valid key still wins, so the demo agent keeps its identity); tools read the agent via `current_agent(ctx)` and never fall back to anonymous when auth is required. `submit_analysis` stores the authenticated name; the caller-supplied `agent_name` only counts for anonymous callers. TC-4, TC-5, TC-6, TC-7, TC-11 (behaviour), TC-13, TC-17 green in `test_auth_api.py` (live app + Postgres; `make test-infra SCENE=api` 24 passed); M1 API integration tests now run with `Settings(auth_required=False)`. Ruff, mypy, config check green; `make check` still stops only at the loop's `.claude/` lock (DR-1). Known follow-up (T-08): the pipeline/e2e/stack scenes and compose need a key or `auth_required=false`.

T-06 ✅ 2026-10-14 — `ArticleService.list_new(cursor, limit, stored_seq)` (explicit cursor > stored position > first-run window; empty page returns the position as cursor); MCP `list_new_articles` reads the agent's stored cursor when no cursor is passed; new tool `ack_cursor(cursor)` → `{cursor}` (forward-only `GREATEST`, idempotent, `invalid_cursor` / `anonymous_agent` errors). TC-9, TC-10, TC-16 green (+ explicit-cursor and anonymous cases) in `test_auth_api.py`, 2 new service unit tests; `make test-infra SCENE=api` 29 passed; tool-list test updated to five tools; mvp design.md tool table notes `ack_cursor`. Ruff/mypy/config green; `make check` blocked only by the loop's `.claude/` lock (DR-1).

T-07 ✅ 2026-10-14 — demo agent: `Settings.api_key` (SecretStr, env `NEWSDOCK_AGENT_API_KEY`, `cursor_file` removed and dropped from the M1 defaults snapshot), `McpApiClient(mcp_url, api_key, agent_name=…)` sends the Bearer header via `streamable_http_client(http_client=httpx2…)`, `list_new_articles(limit)` has no cursor argument, new `ack_cursor`; `AgentLoop` acks only after the whole batch (no ack on a submit failure or scorer crash); `adapters/cursor.py` deleted; `httpx2` declared as a direct dependency (`uv.lock` +2 lines). Findings: (1) the mcp client hides an HTTP 401 inside nested `ExceptionGroup`s as a generic `MCPError` (status lost), so on a group failure the client probes the endpoint once with a plain `httpx` request and raises `Unauthorized` on 401; `__main__` logs a clear message and keeps retrying with the heartbeat (matches TC-14). (2) Latent M1 bug fixed: `ToolCallError` was raised inside the client's task group and surfaced wrapped in a group, so the `SubmitFailed` mapping never fired; the check now runs after the client context. (3) An anonymous agent (auth off, no key) cannot ack: the client tolerates `anonymous_agent` with a warning (each run then re-reads the last hour; analyses upsert). TC-15 (4 loop tests) + client tests green (33 agent unit tests), the M2a cross-app `test_story_agent` passes against the live API; ruff/mypy/config green; `make check` blocked only by the loop's `.claude/` lock (DR-1). Compose still mounts `agent_state` and passes no key: T-08.

T-08 ✅ 2026-10-14 — compose passes `NEWSDOCK_ADMIN_TOKEN` (api) and `NEWSDOCK_AGENT_API_KEY` (agent) from `.env`, drops the `agent_state` volume; `.env.example`, `make agent-create NAME=`, README section + troubleshooting, CLAUDE.md (status, fixed tool name, auth rule), roadmap. Full `make test-infra`: 75 passed, 1 failed (`test_stack` hard-coded head `0003` → `0004`, fixed, scene green 9/9). **Live check TC-14 done** on the real stack (GDELT slots in Postgres, Ollama `llama3.2:3b`): no key → 401, open `GET /api/articles` → 200, `make agent-create` issued the key once; the agent scored batches under its registered name (`demo-financial`, 474 analyses) and the server cursor advanced (1996 → 2396) with no cursor file; recreating the agent container resumed after the acked position; revoking the key made the agent log `the API rejected this agent's key (HTTP 401)` while staying healthy, a new key recovered it; with Postgres down the API answered 503 and the agent kept retrying until it was back. **Finding:** the first live run hit HTTP 429 at the old default of 120/min because the agent opens a new MCP session per call (~4 requests per scored article); default raised to **600/min** (config, yaml, spec number, tests) — root cause (reuse one session per batch) → backlog. Note: a stale `newsdock_agent_state` volume from M1 runs can be deleted (`docker volume rm`). `make check` is blocked only by the loop's `.claude/` lock (DR-1).
