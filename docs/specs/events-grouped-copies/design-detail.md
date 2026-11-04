# Design detail — events-grouped-copies

Reference only; not required reading for approval.

## 1. Schema (migration 0013 `mentions_derived`)

```sql
ALTER TABLE mentions ADD COLUMN derived boolean NOT NULL DEFAULT false;
-- backfill: the link statement of §2 over all rows, then done
```
Forward-only (DR-11): `downgrade` is a documented no-op. `ix_mentions_url_hash (url_hash, event_id)` already serves the link join and the read path. The `sink_rw` / `extractor_rw` style grants need no change (same table).

## 2. Link statement

Run through the sink's adapter (SQL only in `adapters/`), once with a batch filter and once with a copy filter:

```sql
INSERT INTO mentions (event_id, url_hash, url, source_name, mention_time, confidence, ingested_at, derived)
SELECT m.event_id, s.article_id, m.url, m.source_name, m.mention_time, m.confidence, m.ingested_at, true
FROM mentions m
JOIN article_sources s ON s.url_hash = m.url_hash
WHERE s.article_id <> m.url_hash AND NOT m.derived
  AND <filter>      -- (m.event_id, m.url_hash) IN batch   |   m.url_hash = :copy_hash   |  true for the backfill
ON CONFLICT (event_id, url_hash) DO NOTHING
```
Two copies of one story mentioning the same event collapse to one derived row (same key). The canonical's own source row has `article_id = url_hash`, so it never self-links.

## 3. Real mention beats a derived row

`upsert_mentions` today updates only `WHERE mentions.mention_time < excluded.mention_time`. It becomes `WHERE mentions.derived OR mentions.mention_time < excluded.mention_time` and sets `derived = false`, so a real mention of the canonical always flips a derived row to real. A real row is never turned back into derived (the link statement does nothing on conflict).

## 4. API

`_events_for`: the `others` subquery gains `.where(others.derived.is_(False))`. Nothing else: derived rows carry the canonical id, so the join, cap, order and dedupe already apply.

## 5. Sink wiring

- `domain/gdelt.py` mention path: after `upsert_mentions`, call `writer.link_copy_mentions(batch)` (new port method).
- `domain/writer.py`: for every copy (`canonical_id <> url_hash`), also on a redelivery, call `link_mentions_of(copy_hash)` after `insert_source`. Refined 2026-11-04 during T-04: linking only when the source is new would never heal a crash between the source commit and the link; the statement is idempotent and cheap.
- Domain stays pure; both are port methods implemented in `adapters/db.py`.

## 6. Failure table

| Case | Result |
|---|---|
| Mention for an unknown URL | no link; later `insert_source` links it |
| Canonical expires first | cascade removes its sources; derived rows expire by `ingested_at` |
| Replay of the same batch | `DO NOTHING` / unchanged upsert |

## 7. Security

SQL parameterized; no new input surface; no API change.

## 8. Spike result (T-01, 2026-11-04)

The dev database was not running (no containers up), and starting the owner's stack for a read-only count is the owner's call, so **no live reading was taken**. What exists: the sample slot of events-mentions verify F-1, 727 of 2,514 mentions name a copy, so at most about 29% more rows **[verified 2026-11-02, one slot]**; a 7-day total would be about 1.3–2.0 M real rows plus up to about 0.4–0.6 M derived **[assumption]**. The live count and the backfill `SELECT` time move to `/spec-verify` (tests.md Measurements); the link join uses the existing primary key on `article_sources.url_hash` and `ix_mentions_url_hash`, so no new index is planned **[assumption]**.
