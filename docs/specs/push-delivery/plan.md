# push-delivery — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation (2026-10-14)

| # | Check | Method | Result |
|---|---|---|---|
| 1 | AC → test coverage | grep AC column of tests.md | **pass**: AC-1…AC-15 each ≥ 1 TC (22 TCs; TC-21 is the T-01 spike, TC-14 manual) |
| 2 | AC → design / task coverage | grep design.md §7; `Implements:` in tasks/ | **pass**: 15/15 both |
| 3 | Cross-doc names | `sse_fallback_poll_seconds`, `sse_keepalive_seconds`, `sse_max_streams_per_agent`, `subscriptions_max_per_agent`, `subscription_text_max_length`, `articles_new`, `invalid_last_event_id`, `WakeHub`, `StreamLimiter` across spec/design/tests/tasks | **pass** (the earlier `sse_poll_interval_seconds` was removed with the polling ADR) |
| 4 | Proposed ADRs treated as decided | ADR-0018, ADR-0019 | **pass**: both Accepted 2026-10-14; the superseded polling draft was deleted |
| 5 | Untagged claims / invented numbers | cap 5, 20 subscriptions, 200 chars, 15 s, 30 s, few-second latency | **pass**: all listed as provisional targets (spec §6) and as config defaults |
| 6 | Scope leaks from backlog.md | webhook, MCP notifications, demo agent on push, UI, richer filters only under "Out of scope" | **pass** |
| 7 | Open questions / checklist items | grep `- [ ]` in spec/design | **pass with note**: one item (409 at the subscription cap) was never put to the user; it is ticked as a recorded default (R-1, low: configurable `subscriptions_max_per_agent`) |

Open risks carried: the T-01 spike may overturn the cancellation or LISTEN claims (ADR-0018 is the user's choice, so a failed LISTEN spike stops for a decision); `make check` shows the loop's `.claude/` lock (DR-1) until the loop ends.

**Verdict: GO.** `gates.plan: approved`. No design-review.md exists, so nothing to retire.

## Spike first

**T-01** de-risks the two unverified claims the design leans on (design.md §6, spec §3): (1) a FastAPI `StreamingResponse` over an async generator is cancelled when the client disconnects, so the stream's `finally` (cap release) always runs, even with the pure-ASGI auth middleware in front; (2) a dedicated psycopg async connection can `LISTEN` and receive the notification raised by a statement-level trigger with a transition table, once per batch and not for an `ON CONFLICT DO NOTHING` that inserts nothing. If (1) fails the cap release needs another mechanism; if (2) fails ADR-0018 must be revisited with the user.

## Phases and milestones

| Phase | Tasks | Milestone (ACs) | Effort |
|---|---|---|---|
| 0 Spike | T-01 | claims verified | 0.5 d |
| 1 Core | T-02, T-03, T-04 | filter, cap, hub, table + trigger, filtered query (support for AC-2, AC-6, AC-7) | 1.5 d |
| 2 Routes | T-05 | AC-1…AC-4, AC-15 | 1 d |
| 3 Stream | T-06, T-07 | AC-5…AC-13 | 1.5 d |
| 4 Live | T-08 | AC-14, docs | 0.5 d |

## Definition of Done (every task)

Tests first and red→green; `make check` green (the loop's `.claude/` lock is the only known exception, see agent-platform verify); `make test APP=api`, `make test-infra SCENE=api|db` where a task names it; `make config-python` green when a setting is added; docs/ADR updated in the same edit; no secrets.

## Tasks

| Task | Title | Implements | Depends on |
|---|---|---|---|
| T-01 | Spike: streaming cancellation + LISTEN/trigger | AC-6, AC-11 (risk) | none |
| T-02 | Domain: filter, stream cap, wake hub | AC-2, AC-6, AC-13 | T-01 |
| T-03 | Table `subscriptions`, trigger, repo, `key_usable` | AC-1, AC-6, AC-11 | T-02 |
| T-04 | Filtered `list_new` + shared theme prefix | AC-6, AC-7 | T-02 |
| T-05 | Settings, subscription routes, middleware, admin list | AC-1, AC-2, AC-3, AC-4, AC-15 | T-03 |
| T-06 | NOTIFY listener + lifespan | AC-6 | T-03 |
| T-07 | SSE stream endpoint | AC-5…AC-13 | T-04, T-05, T-06 |
| T-08 | Docs, live check, status | AC-14 | T-07 |

## Progress

(none yet)

T-01 ✅ 2026-10-14 — spike on FastAPI/uvicorn, `psycopg` 3.3.6, Postgres 16 (compose), throwaway script in the scratchpad (not committed), both claims **verified**:
1. A `StreamingResponse` over an async generator behind a pure-ASGI middleware (the same shape as `AuthMiddleware`, setting `scope["state"]`) is cancelled when the client disconnects: the generator got `CancelledError` and ran its `finally` within the same second, even while it was sleeping between pings. The cap release therefore belongs in the generator's `finally`.
2. `psycopg.AsyncConnection` (autocommit) + `LISTEN` + `async for n in conn.notifies()` receives the statement-level trigger's `pg_notify`: a 3-row INSERT → exactly **one** notification with payload = max seq; `INSERT … ON CONFLICT DO NOTHING` that inserts nothing → **none**; a mixed batch (one conflict, one new) → one notification with the new row's seq (identity values are consumed by conflicting rows, so seqs have gaps: cursors must use `seq >` never `+1`); inside an open transaction nothing arrives, the notification arrives only **after commit**. Trigger form used: `AFTER INSERT … REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT`, function `SELECT max(seq) INTO m FROM new_rows; IF m IS NOT NULL THEN PERFORM pg_notify(…, m::text)`.
No design change needed; ADR-0018 stands.

T-02 ✅ 2026-10-14 — `domain/subscriptions.py` (`SubscriptionFilter` frozen, `extra=forbid`, strict strings, non-empty, max length via validation context, `*` only as a prefix suffix; `parse_filter(raw, max_length)` raising `InvalidFilter`; `as_query()`, `as_json()`, `split_theme()`) and `domain/streams.py` (`StreamLimiter` with a lock, safe double release, entries dropped at zero; `WakeHub` with a generation counter so a wake during a query is not lost). TC-16, TC-17 and the unit half of TC-13 green (89 API unit tests); ruff, mypy, import-linter green; `make check` blocked only by the loop's `.claude/` lock (DR-1). Note: async unit tests use `@pytest.mark.anyio` with an `anyio_backend` fixture (no pytest-asyncio in the repo).

T-03 ✅ 2026-10-14 — `Subscription` model, Alembic `0005_subscriptions` (table + index, `api_rw` SELECT/INSERT/DELETE, `notify_articles_new()` function and the `articles_notify` statement-level `AFTER INSERT … REFERENCING NEW TABLE` trigger), `adapters/subscriptions_repo.py` (`SqlSubscriptionsRepo`: create/list_own/get_own/delete_own/count_own/exists/list_all, ownership by `agent_id`, malformed ids look absent), domain records `SubscriptionRecord`/`AdminSubscription`/`SubscriptionStore`, `SqlAgentsRepo.key_usable(key_id)`. Side fix (agent-platform bug found while testing): malformed uuids in admin ids (`/api/admin/agents/nope/disable`) would have been a database error / HTTP 500; `adapters/ids.as_uuid` now makes `set_status`/`revoke_key` return False (404). TC-19 (one notification per batch with max seq; none for a no-op conflict; only after commit; works through the `sink_rw` role) and the repo/key_usable tests green (9 tests, Postgres); `make test-infra SCENE=db` 4 passed, `SCENE=api` 38 passed; ruff/mypy/config green; `test_stack` head updated to `0005`. `make check` blocked only by the loop's `.claude/` lock (DR-1).

T-04 ✅ 2026-10-14 — `_apply_filters` now supports the trailing-`*` theme prefix (an `EXISTS` over `unnest(themes) AS t(theme)` with an escaped `LIKE 'prefix%'`; exact themes keep `themes @> ARRAY[value]`), shared by `search_articles` and `list_new`; `SqlArticleRepo.list_new` and `ArticleService.list_new` take optional `theme/domain/text` (default None = M1 behaviour, `seq` order, source counts unchanged). TC-18 (7 Postgres tests: prefix over any theme, `ECONOMY_` not matched by `ECON_*`, exact vs bare prefix, domain/text/AND, literal `%`/`_` in user input, `after_seq` combined with filters, `search_articles` shares the syntax) + a service pass-through unit test green; `make test-infra SCENE=api` 45 passed; ruff/mypy/config green; `make check` blocked only by the loop's `.claude/` lock (DR-1). SQLAlchemy note: `unnest` needs `table_valued("theme").render_derived()` to expose a named column.

T-05 ✅ 2026-10-14 — settings `subscriptions_max_per_agent` (20), `subscription_text_max_length` (200), `sse_max_streams_per_agent` (5), `sse_keepalive_seconds` (15), `sse_fallback_poll_seconds` (30) + their rows in `newsdock.yaml` (`make config-python` green); `AuthMiddleware` now guards `/mcp*` and `/api/subscriptions*` and stores `key_id` next to the agent; `adapters/subscriptions_api.py` (`POST` body = the filter itself → 201 `{id, filter, created_at}`, 422 invalid, 409 `too_many_subscriptions`; `GET` own; `DELETE` own → 204/404; anonymous callers 403 `anonymous_agent`); `GET /api/admin/subscriptions` (admin token; agent key 403; unset token 404); `create_app(settings, agents_repo, subscriptions_repo, key_lookup)` takes injectable stores. TC-1 (API half; persistence is TC-1's repo test from T-03), TC-2, TC-3 (list part), TC-4, TC-5 (route part), TC-15, TC-22 green as 13 unit tests over fakes (103 API unit tests); `SCENE=api` 45 passed; ruff/mypy/config green; `make check` blocked only by the loop's `.claude/` lock (DR-1).

T-06 ✅ 2026-10-14 — `adapters/listener.py`: `NotifyListener` (dedicated `psycopg.AsyncConnection`, autocommit, `LISTEN articles_new`, `connected` event, wakes the hub on every notification and once on every (re)connect, reconnects with doubling backoff 1 s → 30 s, clean `CancelledError`), `listen_dsn()` (SQLAlchemy URL → conninfo URL, password kept); `create_app` builds one `WakeHub` (`app.state.wake_hub`) and starts/stops the listener in the lifespan; `psycopg>=3.2` declared in `apps/api/pyproject.toml` (`uv.lock` +4 lines). TC-20 (listener half) green: notification wakes two waiting streams, a no-op conflict wakes none, killing the listener backend makes it reconnect and wake everyone and it keeps working, cancel is clean (4 Postgres tests); `make test-infra SCENE=api` 49 passed, `SCENE=e2e` 9 passed; ruff/mypy/config green; `make check` blocked only by the loop's `.claude/` lock (DR-1). The fallback-poll half of TC-20 lives in the stream (T-07).

T-07 ✅ 2026-10-14 — `adapters/sse.py` `build_stream_router`: `GET /api/subscriptions/{id}/stream` (`text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`); frames `id: <cursor>` / `event: article` / `data: <ArticleSummary json>`; start position `Last-Event-ID` > stored server cursor > first-run window (stored cursor only read when no Last-Event-ID, never written); loop = note `hub.generation()` → `service.list_new(cursor, limit 200, filter)` → emit → `hub.wait(keepalive)`; on a quiet tick sends `: ping` and re-checks `key_usable(key_id)` and `subscriptions.exists` (stream ends if either fails), re-queries on wake or after `sse_fallback_poll_seconds`; errors: foreign/malformed id 404, bad `Last-Event-ID` 400 `invalid_last_event_id`, over the cap 429 + `Retry-After: 5`, anonymous 403; the stream slot is released exactly once by the generator's `finally` and by a `BackgroundTask` (covers a generator that never started). Wired in `create_app` with the shared `WakeHub` and a `StreamLimiter`. `test_stream_api.py` (10 live-app Postgres tests) green: TC-5, TC-3 (stream), TC-6 + TC-7 (delivered via NOTIFY within seconds with a 60 s fallback), TC-8, TC-9 + TC-10, TC-12, TC-11 (revoked key and deleted subscription end the stream; reconnect 401), TC-13 (cap, other agent unaffected, slot freed after close), TC-20 fallback (killed listener connection, delivery continues). `make test-infra SCENE=api` 59 passed; ruff/mypy/config green; `make check` blocked only by the loop's `.claude/` lock (DR-1).

T-08 ✅ 2026-10-14 — README section (subscriptions, streams, curl examples, limits, troubleshooting), CLAUDE.md (status, push rule), roadmap. Full `make test-infra`: **107 passed**. **Live check TC-14 done** on the real stack (compose `--profile apps`, real GDELT, migration 0005 applied): with an ECON_* subscription and a never-matching one streaming via `curl -N`, the ingester published real slot 20261014134500 (1,440 rows); the ECON_* stream received **266 events with 266 distinct article ids = the 266 ECON_ rows the DB stored in that window**, each with `id:` cursor, `event: article` and summary JSON; the unrelated stream stayed silent; an idle stream sent `: ping` every ~15 s (3 in 50 s); `Last-Event-ID` = first id → 265 events, = last id → 0, garbage → 400; the stored agent cursor stayed untouched; after an API restart both subscriptions survived and the open streams dropped. **Finding fixed:** the revoked-key/deleted-subscription re-check only ran on quiet ticks, so steady NOTIFY wake-ups (a busy sink) could starve it; it now runs on its own `sse_keepalive_seconds` timer; regression test `test_revocation_is_noticed_under_constant_traffic` added (11 stream tests green). Note: a stale `newsdock-push-test` compose project can remain after a failed fixture run (`docker compose -p newsdock-push-test down -v`).
