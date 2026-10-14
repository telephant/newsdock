# agent-platform — Tests

Spec: [spec.md](spec.md) · Design: [design.md](design.md)

**Fixtures:** no GDELT data needed. Unit tests use fakes (in-memory registry, fake clock). Integration tests use the existing API test harness (`apps/api/tests/integration`, real Postgres) and seed articles through the repo as `test_mcp_api.py` does. Agent unit tests fake `McpApiClient` as `test_loop.py` does. Test keys and tokens are generated in-test, never committed.

| TC | AC | Level | Case (Given / When / Then) |
|---|---|---|---|
| TC-1 | AC-1 | integration | Given admin token set; When POST `/api/admin/agents {name}`; Then 201 with `agent_id` and `api_key`; GET `/api/admin/agents` shows the agent and prefix but no key; a duplicate name → 409 |
| TC-2 | AC-2 | integration | Given an issued key; When `api_keys` row is read; Then `key_hash` is a sha256 hex and ≠ the secret, `prefix` is stored, the plaintext appears in no column |
| TC-3 | AC-2 | unit | `make_key`/`parse_key`/`hash_secret`/`verify`: format `ndk_<prefix>_<secret>`, round-trip, malformed strings rejected, wrong secret fails, comparison uses `hmac.compare_digest` |
| TC-4 | AC-3 | integration | Given `auth_required=true`; When MCP `list_new_articles` is called with no header, a malformed header, and an unknown key; Then HTTP 401 each time and no tool ran (no cursor/analysis side effect) |
| TC-5 | AC-4 | integration | Given an active agent and key; When `search_articles` is called over MCP with the key; Then it succeeds and returns the seeded articles |
| TC-6 | AC-5 | integration | Given a revoked key, and separately a disabled agent; When each calls an MCP tool; Then 401; re-enabling the agent restores access, a revoked key stays rejected |
| TC-7 | AC-6 | integration | Given agent "alpha"; When `submit_analysis(agent_name="beta")`; Then the stored `analyses.agent_name` is "alpha" |
| TC-8 | AC-7 | integration | Given admin routes; When called with no token, with an agent key, with a wrong token; Then 401 / 403 / 401 and the registry is unchanged; with `NEWSDOCK_ADMIN_TOKEN` unset every admin route is 404 |
| TC-9 | AC-8 | integration | Given alpha called `list_new_articles` then `ack_cursor(next_cursor)`; When a fresh MCP session of alpha calls `list_new_articles` with no cursor; Then only articles after the acked position are returned; without the ack the same batch returns again |
| TC-10 | AC-9 | integration | Given alpha acked cursor C; When beta (new agent, no stored cursor) calls `list_new_articles`; Then beta gets the first-run window, not the C-based view |
| TC-11 | AC-10 | integration + check | Given `auth_required=false`; When an MCP tool is called with no key; Then success as `anonymous`; `ack_cursor` → ToolError `anonymous_agent`; `submit_analysis` keeps the caller-supplied name. And `infra/config/newsdock.yaml` lists `auth_required: true`, `make config-python` is green |
| TC-12 | AC-11 | unit | Fixed-window limiter with a fake clock: N allowed, N+1 denied with correct `retry_after`, window rollover resets, agents isolated, `0` disables, anonymous uses one shared bucket (D-8) |
| TC-13 | AC-11 | integration | Given limit N; When alpha sends N+1 MCP requests in one minute and beta sends one; Then alpha's N+1th is 429 with `Retry-After`, beta succeeds |
| TC-14 | AC-12 | manual | See checklist below |
| TC-15 | AC-8, AC-12 | unit | Agent loop with a fake client: `ack_cursor(next_cursor)` is called only after all submits succeed; a submit failure or Ollama error means no ack; no cursor file is read or written |
| TC-16 | AC-8 | integration | `ack_cursor` is forward-only (a lower cursor is a no-op), idempotent, and an invalid cursor → ToolError `invalid_cursor` |
| TC-17 | AC-2 | unit | Logging: with log capture at DEBUG, issuing a key and calling with it never emits the secret or the admin token (only the prefix) |
| TC-18 | AC-3, AC-4 | spike | T-01: the middleware-verified agent reaches a tool through `ctx.request_context.request.state`, and the agent's MCP client can send an `Authorization` header (result recorded in plan.md; becomes TC-4/TC-5 fixtures) |

## Manual checklist — TC-14 (AC-12)

- [x] `.env` has `NEWSDOCK_ADMIN_TOKEN`; `make up`; create agent `demo` via the admin route (`make agent-create NAME=demo`); put the key in `.env` as `NEWSDOCK_AGENT_API_KEY`; restart the agent.
- [x] Agent logs show a scored batch; `/api/articles/{id}` shows analyses with agent name `demo`.
- [x] Remove the agent container and start it again: it resumes after the acked cursor (no re-scoring of the old batch) and no cursor file exists on any volume.
- [x] Revoke the key: the agent logs 401 and keeps retrying without crashing; issue a new key and it recovers.
- [x] Web UI still lists articles with no key.

## Measurements (provisional targets — not pass/fail)

| What | How |
|---|---|
| Default rate limit sufficient for the demo agent | Count MCP requests per minute in a live loop (list + N submits + ack) and compare to the limit | Measured 2026-10-14: ~4 requests per scored article (new session per call), so the 120/min start value was too low and the default is now 600 |
| Auth overhead per request | Time `verify` + DB lookup over 1000 calls in a script |
| Key entropy | Assert secret length ≥ 32 random bytes in TC-3 (a unit-level fact, recorded here) |
