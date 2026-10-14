# agent-platform — Verification

Date: 2026-10-14 · Spec: [spec.md](spec.md) · Tests: [tests.md](tests.md) · Verdict: **pass with follow-ups**

## Run summary (this session, after the last code change)

| Check | Result |
|---|---|
| `uv run pytest` (unit, all packages) | 326 passed, 1 failed: `test_check_layout::test_real_repo_passes` — only because the /loop harness wrote `.claude/scheduled_tasks.lock` at the repo root (DR-1) |
| `make check` | ruff, ruff format, mypy (160 files), import-linter (4 contracts), `check_config`, web lint/format/types/tests (13) all pass; only `layout-python` fails on that lock file. A copy of the repo without `.claude/` passes `check_layout.py` (exit 0) |
| `make test-infra` (all Docker scenes) | **76 passed**, exit 0 (db, kafka, sink, api 29, pipeline, e2e, stack, images) |
| Live stack (TC-14) | done 2026-10-14 on real GDELT data + Ollama, details below |

## Acceptance criteria

| AC | TC | Result | Evidence |
|---|---|---|---|
| AC-1 create agent and key | TC-1 | pass | `test_admin.py` (201, key once, listing hides it, 409/422); live: `make agent-create` printed the key once |
| AC-2 keys stored hashed | TC-2, TC-3, TC-17 | pass | `test_agents_repo.py::test_key_is_stored_hashed`, `test_agents.py`, `test_auth_api.py::test_secrets_are_not_logged` |
| AC-3 missing/wrong key → 401 | TC-4 | pass | `test_auth_api.py::test_missing_malformed_or_unknown_key_is_401`; live: no key → 401 |
| AC-4 valid key accepted | TC-5 | pass | `test_valid_key_can_search`; live agent batches |
| AC-5 revoked/disabled → 401 | TC-6 | pass | `test_revoked_and_disabled`; live: revoked key → agent logged 401, new key recovered |
| AC-6 identity on analyses | TC-7 | pass | `test_analysis_carries_the_authenticated_identity`; live: 474 analyses under `demo-financial` |
| AC-7 admin token required | TC-8 | pass | `test_admin.py` (401/403/404 matrix, registry unchanged) |
| AC-8 server cursor resumes | TC-9, TC-16, TC-15 | pass | `test_server_cursor_resumes_after_ack`, ack tests, `test_loop.py`; live: cursor 1996 → 2396, container recreated and resumed |
| AC-9 cursors independent | TC-10 | pass | `test_cursors_are_independent` |
| AC-10 auth off by config | TC-11 | pass | `test_auth_off_is_anonymous`, `test_anonymous_cannot_ack`, config tests; `auth_required: true` in `newsdock.yaml`, `make config-python` green |
| AC-11 rate limit isolates agents | TC-12, TC-13 | pass | `test_ratelimit.py`; `test_rate_limit_isolates_agents` (429 + `Retry-After`, other agent unaffected) |
| AC-12 demo agent end to end | TC-14 (manual), TC-15 | manual-ok | Live run, checklist all ticked (below) |

### TC-14 live evidence
Stack: compose with `--profile apps`, 1,796+ real articles, Ollama `llama3.2:3b`. No key → 401; `GET /api/articles` without key → 200; agent scored batches (48/57/49/51 of 200 per batch) and the web UI answered 200; recreating the agent container resumed after the acked cursor; no cursor file (`agent_state` volume no longer mounted); revoke → "the API rejected this agent's key (HTTP 401)" with the container still `healthy`; new key → recovered; Postgres down → API 503, agent kept retrying, recovered when Postgres returned.

## Measurements (provisional targets, not pass/fail)

| What | Measured | Note |
|---|---|---|
| Requests per scored article | ~4 (a new MCP session per call) | The first live run hit 429 at the old 120/min default; default raised to 600/min. Root cause (reuse one session per batch) is a backlog item |
| Auth overhead per request | 0.98 ms/call (1000 calls: prefix lookup + sha256 + `hmac.compare_digest`, local Postgres) | |
| Key entropy | 256-bit secret (32 random bytes, hex), asserted in TC-3 | |

## Doc drift

Fixed in this run: `design-detail.md` §3 (a valid key still wins when `auth_required=false`), §5 (missing key = warning and retry, not a startup error), ADR-0016 wording, spec assumption tags (middleware and header claims now **[verified]**), rate-limit default 120 → 600 in design, spec and tests, `CLAUDE.md` (status, `ack_cursor`, auth rule), README (auth section, `make agent-create`, troubleshooting), `docs/specs/mvp/design.md` tool table (`ack_cursor`).
Open (accepted): `docs/specs/mvp/design.md` F-2 and `design-detail.md` still describe the M1 cursor file; they are the M1 record and now carry a note.

## Scope

Nothing from `backlog.md` leaked in (no filters, push, UI login, rotation, scopes, volume quotas). Additions beyond the spec that the tasks required: `make agent-create` target, tolerance of `anonymous_agent` on ack in the agent client, and a fix for a latent M1 bug (tool errors wrapped in an exception group, so `SubmitFailed` never fired).

## Follow-ups (moved to backlog)

1. Agent: reuse one MCP session per batch (P2, already added).
2. Reads stay open until `ui-login` (spec D-7, accepted risk R-1).
3. The layout rule DR-1 flags `.claude/` created by Claude Code's /loop; allow it in `check_layout.py` or delete the lock when the loop ends (P3).
4. A stale `newsdock_agent_state` Docker volume may remain on machines that ran M1 (`docker volume rm`).
