# ADR-0018: SSE streams wake on Postgres `LISTEN/NOTIFY`, and still read by `seq`

Status: **Accepted 2026-10-14** (user chose `LISTEN/NOTIFY` at /spec-design push-delivery over the recommended per-stream polling)

## Context
Push needs the API to notice articles written by the sink, a separate process (spec §8, risk 2). Articles arrive in bursts about every 15 minutes (GDELT slots). The API runs one worker and caps open streams per agent.

## Options
(a) Each stream polls `articles` for `seq > last_sent` every few seconds (the recommended, simplest option).
(b) **A trigger on `articles` sends `pg_notify('articles_new', <max seq>)`; one listener connection in the API wakes the open streams; each stream then runs its filtered `seq > last_sent` query.**
(c) A shared in-process broker that polls once and fans out.

## Decision
(b). The notification is only a **wake-up**, never the data: the stream's truth stays the cursor query (`seq` order, filters, source counts), so a lost or duplicated notification cannot cause a gap or a wrong row. Details:
- Migration 0005 adds a statement-level `AFTER INSERT` trigger on `articles` using a transition table, so a 200-row sink batch sends **one** notification; an `ON CONFLICT DO NOTHING` statement that inserts nothing sends none.
- The API holds one dedicated `LISTEN articles_new` connection (started in the app lifespan) and a pure in-process hub that wakes every waiting stream.
- A slow **fallback poll** (`sse_fallback_poll_seconds`, default 30) covers notifications missed while the listener reconnects; on every (re)connect the hub wakes all streams once.
- The keep-alive tick (ADR-0019) doubles as the wait timeout.

## Consequences
Delivery latency is about the query time after commit instead of up to a poll interval, and idle streams cost no queries. In return: a trigger in the schema (sink writes become very slightly more expensive), a long-lived listener connection to supervise (reconnect with backoff), and notifications are lost on a listener outage (covered by the fallback poll and the reconnect wake-up). `NOTIFY` fires only after commit, so streams never see uncommitted rows. A late-committed lower `seq` could be missed if two writers overlap; the sink is the single writer **[verified: M1 design]**. If streams ever number in the hundreds, the hub is the extension point.
