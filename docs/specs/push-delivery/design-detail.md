# push-delivery — Design detail

Reference only; not required reading for approval.

## 1. Domain

`SubscriptionFilter(BaseModel, extra="forbid")`: `theme: str | None`, `domain: str | None`, `text: str | None`; each non-empty, ≤ `subscription_text_max_length`; stored as JSON with only the fields given. Theme `ECON_*` → prefix `ECON_`; a `*` anywhere but the end is rejected (422). Matching is SQL only.

`StreamLimiter(max_streams)`: `try_acquire(agent_id) -> bool`, `release(agent_id)`; thread-safe counter dict; entries removed at zero. Pure, tested with fakes.

## 2. Stream algorithm (C-16)

```
open(agent, subscription_id, last_event_id):
  sub = repo.get_own(agent.id, subscription_id)       -> 404 if None
  if last_event_id: after = decode_cursor(it)         -> 400 if invalid
  elif stored cursor exists: after = stored
  else: after = None, since = now - first_run_window
  if not limiter.try_acquire(agent.id): 429
  try:
    loop:
      batch = list_new(after, since, limit=200, **sub.filter)   # threadpool
      for a in batch: emit id=encode_cursor(a.seq), data=a; after = a.seq; since = None
      if batch full: continue (no wait)
      woke = hub.wait(timeout=keepalive)        # NOTIFY wake-up, or timeout
      if not woke: emit ": ping"
      if now - last_check >= keepalive:           # on a timer, even under steady wake-ups
         last_check = now
         if not key_usable(key_id) or not sub_exists: break
      # a fallback poll also happens at most every sse_fallback_poll_seconds
  finally: limiter.release(agent.id)
```

If `after` is None and `since` is set, the first query uses the first-run window; afterwards position is always a `seq`. Events for one article carry its own cursor, so a client may resume from any event.

## 2b. NOTIFY trigger and listener (C-18)

Migration 0005:
```sql
CREATE FUNCTION notify_articles_new() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m bigint;
BEGIN
  SELECT max(seq) INTO m FROM new_rows;
  IF m IS NOT NULL THEN PERFORM pg_notify('articles_new', m::text); END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER articles_notify AFTER INSERT ON articles
  REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION notify_articles_new();
```
Statement-level with a transition table: one notification per sink batch; an `ON CONFLICT DO NOTHING` statement that inserted nothing sends none. The listener (`adapters/listener.py`) opens its own autocommit psycopg connection, `LISTEN articles_new`, and for every notification calls `hub.wake_all()`; on error it sleeps with backoff (1 s doubling to 30 s), reconnects, re-LISTENs and calls `hub.wake_all()`. It starts and stops in the FastAPI lifespan next to the MCP session manager. The `autogenerate` no-op test is unaffected (triggers are not in the metadata) but the migration test checks the trigger exists.

## 3. SQL changes

`_apply_filters` gains prefix handling: a theme ending in `*` becomes `EXISTS (SELECT 1 FROM unnest(articles.themes) t WHERE t LIKE :prefix ESCAPE '\')` with `escape_like(prefix) + '%'`; otherwise `themes @> ARRAY[:theme]` as today. `list_new(after_seq, since, limit, theme=None, domain=None, text=None)` applies the same filters, keeps `ORDER BY seq`, source counts as before.

## 4. Auth middleware changes

`PROTECTED = ("/mcp", "/api/subscriptions")`; `scope["state"]["key_id"]` is set next to `agent` (None for anonymous). With `auth_required=false`, anonymous callers cannot own subscriptions: routes answer 403 `anonymous_agent` (they have no id to attach rows to).

## 5. Admin route

`GET /api/admin/subscriptions` → `[{id, agent_id, agent_name, filter, created_at}]` behind the existing admin dependency.

## 6. Failure table (full)

| Case | Handling |
|---|---|
| Unknown subscription / other agent's | 404 (no existence leak) |
| Over `subscriptions_max_per_agent` | 409 `too_many_subscriptions` |
| Over `sse_max_streams_per_agent` | 429 with `Retry-After: 5` |
| Bad `Last-Event-ID` | 400 `invalid_last_event_id` |
| Subscription deleted while streaming | loop exits at the next keep-alive tick |
| Agent disabled / key revoked | loop exits at the next re-check (≤ `sse_keepalive_seconds`, 15 s by default, also under constant NOTIFY traffic) |
| DB unavailable in the loop | stream closes; client reconnects with its last id |
| Listener connection down | streams keep working on the fallback poll (`sse_fallback_poll_seconds`); on reconnect everyone is woken |
| Notification arrives before the commit is visible to the stream's query | impossible: `NOTIFY` is delivered after commit |
| Proxy buffering | not applicable locally; send `X-Accel-Buffering: no` and `Cache-Control: no-cache` |

## 7. Security notes

Ownership checked on every route by `agent_id`; 404 not 403 for others' ids. Filter text is only ever a bound parameter. No secrets in events or logs; the keep-alive interval bounds how long a revoked key keeps a stream. Browsers' `EventSource` cannot send `Authorization`, so streams are for programmatic clients; the UI gets its own mechanism in `ui-login`.
