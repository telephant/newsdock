# Design — events-grouped-copies (M3e)

Reading order: this file → `diagrams/index.html` (components, sequence, data model) → ADR-0038 → `design-detail.md` (reference only).

## Idea

A copy's mention gets a **derived row** in `mentions` that names the canonical (`url_hash` = canonical id, `derived = true`). The API's `_events_for` already finds events by `mentions.url_hash IN article ids`, so the read path does not change except that `mention_count` ignores derived rows. Derived rows are written by the sink at two moments (a mention arrives; a URL becomes a copy) and once by migration 0013 for rows already stored.

## Components (existing ids from events-mentions; no new service)

| Id | Job | Change |
|---|---|---|
| C-4 sink | upserts articles, sources, events, mentions | after a mentions batch and after `insert_source`, run one `INSERT … SELECT` that adds derived rows |
| C-5 Postgres | `mentions` | migration 0013: column `derived boolean not null default false`, plus the backfill (same `INSERT … SELECT`) |
| C-6 API | `_events_for` | `mention_count` counts `derived = false` only; nothing else |
| retention | deletes mentions by `ingested_at` | none: a derived row copies the source mention's `ingested_at`, so both expire together |

## Key flows

1. **Mention after grouping:** sink upserts the batch → derived rows for those whose `url_hash` is a copy (diagram 2).
2. **Mention before grouping:** the sink stores a copy (also on a redelivery) → derived rows for the copy's stored mentions (diagram 2).
3. **Backfill:** migration 0013 runs the same statement over all rows.
4. **Read:** unchanged query; derived rows look like the canonical's own mentions, so AC-5 dedup is the primary key `(event_id, url_hash)`.

## Contract

| Item | Value |
|---|---|
| New column | `mentions.derived` boolean, default false |
| Derived row | PK `(event_id, canonical_id)`, `url` = copy's URL, other fields copied from the source mention, `ingested_at` copied |
| Link statement | `INSERT … SELECT … JOIN article_sources s ON s.url_hash = m.url_hash WHERE s.article_id <> m.url_hash AND NOT m.derived … ON CONFLICT DO NOTHING` |
| Real beats derived | the mentions upsert also sets `derived = false` when it hits a derived row (a real mention of the canonical must count) |
| `mention_count` | rows with `derived = false` for the event |

## Tricky parts

- **Order:** both orders of mention and grouping are covered by the two triggers; every write is `ON CONFLICT DO NOTHING`, so replays and double triggers are harmless (AC-7).
- **Real vs derived on one key:** a derived row may exist when the canonical's own mention arrives; the upsert's `WHERE` must also fire on `derived` (design-detail §3).
- **Retention:** copying `ingested_at` keeps AC-8 free of a new delete.
- **Regrouping:** copies are never moved once linked (`insert_source` is `ON CONFLICT DO NOTHING`), so no unlinking is needed. A deleted canonical's derived rows expire by `ingested_at` **[verified in code 2026-11-04: sources only insert once]**.

## Failure modes

| Failure | Effect |
|---|---|
| Link statement fails | sink batch fails and is retried (at-least-once); idempotent |
| Migration backfill slow | one pass over about 2 M mentions, joined by index on `article_sources` **[assumption]**; measure at verify |
| Derived rows inflate storage | at most about 29% more rows **[assumption]**; measure |

## Technology

Postgres, SQLAlchemy 2, Alembic; no new library.

## AC coverage

| AC | Where |
|---|---|
| AC-1, AC-9, AC-10 | C-6 read path + derived rows (flow 1, 4) |
| AC-2 | C-4 `insert_source` trigger (flow 2) |
| AC-3 | C-5 migration 0013 backfill (flow 3) |
| AC-4 | C-6 `mention_count` filter |
| AC-5 | PK + `ON CONFLICT DO NOTHING` |
| AC-6 | unchanged cap and order in `_events_for` |
| AC-7 | `ON CONFLICT DO NOTHING` on every link write |
| AC-8 | copied `ingested_at`, existing retention |

## Questions to answer before approving this design

- [x] Derived rows live in `mentions` with a flag (ADR-0038 option a), not in a side table?
- [x] Is the write-time design still preferred over the read-time join (ADR-0038 option c, no migration, no sink change)? See ADR for the trade.
- [x] The backfill runs inside migration 0013 (so `make migrate` does it)?
- [x] `mention_count` stays "real stored mentions" (flag filter)?
