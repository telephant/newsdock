# push-delivery — Tests

Spec: [spec.md](spec.md) · Design: [design.md](design.md)

**Fixtures:** no GDELT data. Unit tests use fakes (in-memory repos, fake clock, a fake hub). Integration tests reuse the `agent-platform` harness (`apps/api/tests/integration`, real Postgres via compose project `newsdock-push-test`, live uvicorn on a free port, `httpx` streaming for SSE). Articles are seeded with SQLAlchemy exactly as in `test_auth_api.py`; agents and keys are created with `SqlAgentsRepo`. Test keys/tokens are generated in-test.

| TC | AC | Level | Case (Given / When / Then) |
|---|---|---|---|
| TC-1 | AC-1 | integration | Given agent alpha; When `POST /api/subscriptions {"theme":"ECON_*","domain":"example.com"}`; Then 201 with `id` and the stored filter; a second app instance on the same DB (a "restart") still lists it |
| TC-2 | AC-2 | integration | Given alpha; When filters with an unknown field, a number value, text over `subscription_text_max_length`, a `*` in the middle of a theme, or an empty string are posted; Then 422 each and nothing stored; the (cap+1)th subscription → 409 |
| TC-3 | AC-3 | integration | Given alpha and beta each with a subscription; When alpha lists and requests `GET /api/subscriptions/{beta_sub}/stream`; Then the list has only alpha's and the stream request is 404 |
| TC-4 | AC-4 | integration | Given alpha and beta each with a subscription; When alpha deletes its own then beta's id; Then 204, then 404, and beta's row still exists |
| TC-5 | AC-5 | integration | Given a subscription and `auth_required=true`; When its stream (and `POST/GET/DELETE /api/subscriptions`) is called with no key, an unknown key, a revoked key; Then 401 and no event bytes |
| TC-6 | AC-6 | integration | Given an open stream for `{"domain":"example.com"}`; When the test inserts an article from example.com (a normal commit); Then within a few seconds one `event: article` arrives with `data` = the summary and `id` = `encode_cursor(seq)` |
| TC-7 | AC-7 | integration | Given the same open stream; When an article from other.org is inserted; Then no event is emitted for it: a matching article inserted right after arrives as the next and only event |
| TC-8 | AC-8 | integration | Given a stream delivered events up to id E and closed, and two matching articles inserted meanwhile; When reconnecting with `Last-Event-ID: E`; Then exactly those two arrive in order, none at or before E; a malformed id → 400 `invalid_last_event_id` |
| TC-9 | AC-9 | integration | Given agent A with stored cursor C and agent B with none; When each opens a stream without `Last-Event-ID`; Then A first receives matching articles after C, B receives matching articles from the first-run window |
| TC-10 | AC-10 | integration | Given an agent that received events; When `agent_cursors` is read; Then unchanged until `ack_cursor` is called |
| TC-11 | AC-11 | integration | Given an open stream; When the key is revoked (or the agent disabled); Then the server ends the stream within ~`sse_keepalive_seconds` (test uses a 1 s interval) and a reconnect is 401; deleting the subscription also ends it |
| TC-12 | AC-12 | integration | Given an open idle stream and `sse_keepalive_seconds=1`; When 2 s pass; Then a `: ping` comment line arrives |
| TC-13 | AC-13 | unit + integration | Unit: `StreamLimiter` allows N then denies, release frees a slot, agents isolated, double release is safe. Integration: alpha opens N streams, the N+1th is 429, beta opens one fine, closing one of alpha's frees a slot |
| TC-14 | AC-14 | manual | See checklist below |
| TC-15 | AC-15 | integration | Given subscriptions of alpha and beta; When `GET /api/admin/subscriptions` is called with the admin token, an agent key, and nothing; Then both agents' rows with agent names, 403, 401 |
| TC-16 | AC-2 | unit | `SubscriptionFilter`: valid fields, `extra=forbid`, empty/over-long/non-string rejected, `*` only as the last character of `theme`, empty filter allowed, `as_query()` yields the `list_new` arguments |
| TC-17 | AC-6 | unit | `WakeHub`: a waiter returns `True` on `wake_all`, `False` on timeout; several waiters all wake; a wake before the wait is not lost (generation counter) |
| TC-18 | AC-6, AC-7 | integration | `list_new(after_seq, since, limit, theme, domain, text)` returns only matching rows in `seq` order; theme `ECON_*` matches by prefix on any of the article's themes, exact theme matches exactly; the same prefix works in `search_articles` (D-7) |
| TC-19 | AC-6 | integration | Migration 0005 trigger: one multi-row INSERT sends exactly one `articles_new` notification carrying the max `seq`; an `INSERT … ON CONFLICT DO NOTHING` that inserts nothing sends none; notifications arrive only after commit |
| TC-20 | AC-6 | integration | Listener: a notification wakes a waiting stream; killing the listener connection makes streams still deliver via the fallback poll, and the reconnect wakes everyone |
| TC-21 | AC-6, AC-11 | spike | T-01: async-generator streaming responds to client disconnect (cancellation reaches `finally`) through the pure-ASGI middleware, and psycopg async `LISTEN` receives `pg_notify` from the trigger (recorded in plan.md Progress 2026-10-14: verified; becomes TC-19/TC-20 fixtures) |
| TC-22 | AC-1 | integration | Given `auth_required=false`; When an anonymous caller uses the subscription routes; Then 403 `anonymous_agent` |

## Manual checklist — TC-14 (AC-14)

- [x] Stack up with `--profile apps`, an agent and key from `make agent-create`.
- [x] `curl -H "Authorization: Bearer $KEY" -X POST …/api/subscriptions -d '{"theme":"ECON_*"}'`, then `curl -N -H "Authorization: Bearer $KEY" …/api/subscriptions/<id>/stream`.
- [x] A second subscription with a filter that matches nothing (e.g. `{"domain":"nonexistent.invalid"}`) stays silent.
- [x] Wait for a real GDELT slot (or force one with the ingester's re-ingest path): events with `id:` lines appear on the first stream within seconds of the sink commit; `: ping` lines arrive while idle.
- [x] Ctrl-C and reconnect with `-H "Last-Event-ID: <last id>"`: only newer articles arrive.
- [x] Restart the API container: the stream drops, the subscription survives, reconnecting works.

## Measurements (provisional targets — not pass/fail)

| What | How |
|---|---|
| Delivery latency (commit → event) | Insert a row in a test, timestamp it and the event arrival; 100 samples. Observed 2026-10-14: stream tests receive events within ~1 s of commit with a 60 s fallback poll (so via NOTIFY); not sampled 100× |
| Keep-alive interval suitability | Idle stream through the real stack for 5 min; confirm no drops |
| Concurrent-stream cap, subscription cap, filter length | Review against the live run; adjust defaults if the demo needs more |
| Fallback poll interval | Kill the listener in a test; measure worst-case delivery delay |
| Query cost per wake-up | `EXPLAIN ANALYZE` of the filtered `list_new` on the live table size |
