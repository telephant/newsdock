# ADR-0038: Derived mention rows link a story's copies to the canonical article

Status: **Accepted 2026-11-04** (confirmed by the user during `/spec-design`; spec `events-grouped-copies`, D-1 to D-5). Amends the last-but-one consequence of ADR-0033 ("events of grouped copies are not shown"); ADR-0033 stays Accepted and unchanged otherwise.

## Context
`articles` holds only canonicals; copies of a story are in `article_sources` (which also holds each canonical's own URL). Mentions name any URL, so those naming a copy never reach the canonical (events-mentions verify F-1: 26 of 996 events, 727 of 2,514 mentions in the sample slot, 5 of 778 canonicals affected). The user chose a write-time link (D-1).

## Options
- **(a) Derived rows in `mentions`** with `derived boolean`, written by the sink when a mention arrives or a copy is grouped, and by migration 0013 for stored rows; `mention_count` filters them out.
- **(b) A side table** `mention_links (event_id, article_id)`; keeps `mentions` pure, but needs a union in the API and its own retention.
- **(c) Read-time join** in `_events_for`: `mentions JOIN article_sources ON url_hash`, grouped by the canonical's id. No migration, no sink change, no backfill, correct for past and future grouping.

## Decision
**(a)**, as the user decided write time. The flag is a boolean on the existing table; the link statement is one idempotent `INSERT … SELECT … ON CONFLICT DO NOTHING`; `ingested_at` is copied so retention is unchanged.

## Consequences
+ Read path and caps unchanged; `include=events` costs no extra join.
+ Replays and both arrival orders are safe.
− A migration, a backfill and two new sink calls; derived rows raise storage by up to about 29% **[assumption]**, measured at verify.
− Two meanings in one table; every reader of `mentions` must remember `derived` (today only `_events_for`'s count).
− **Honest note:** (c) reaches the same result with far less machinery (the data to join already exists, 970 of 996 sample events are linked through `article_sources`). It was kept as the fallback; choose it at approval if the write-time cost looks too high.
