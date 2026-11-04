# Design — events-mentions (M3c)

Spec: [spec.md](spec.md). Detail (not required for approval): [design-detail.md](design-detail.md). Diagrams: [diagrams/index.html](diagrams/index.html). Decisions: [ADR-0032](../../adr/0032-events-mentions-ride-the-existing-pipeline-tagged-by-kind.md), [ADR-0033](../../adr/0033-events-mentions-tables-joined-to-articles-by-url-hash.md) (both Accepted 2026-11-02).

Reading order: this file → diagrams → the two ADRs. Code facts below were read from the repo on 2026-11-02 **[verified]**; data facts are in spec §3.

## Idea in four lines

1. The ingester fetches the Events and Mentions files of a slot next to GKG, each with its own retry state, and publishes their lines on the **existing** raw topic with a `kind` tag.
2. The processor routes by `kind`: GKG as today, Events and Mentions to two new clean topics, bad rows to the existing dead-letter topic.
3. The sink upserts into two new tables and deletes old rows with the same retention job.
4. The API reads an article's events through the mentions table (`mention_url_hash` → `event_id`) and adds them when `include` contains `events`.

## Components

| Id | Job | Change |
|---|---|---|
| C-1 | Ingester | Also fetches `*.export.CSV.zip` and `*.mentions.CSV.zip`; state per file in the new `ingest_file` table; `ingest_slot` and GKG unchanged |
| C-2 | Kafka | `gkg.raw` and `gkg.dlq` carry all kinds; new topics `events.clean`, `mentions.clean` (names are settings, ADR-0013) |
| C-3 | Processor | `route()` dispatches on `kind`: `parse_event_row`, `parse_mention_row` in `newsdock_core` |
| C-4 | Sink | Subscribes to three clean topics; two new writers; retention deletes both tables |
| C-5 | Postgres | New tables `events`, `mentions`, `ingest_file` (migration 0011), grants for `ingester_rw`, `sink_rw`, `api_rw` |
| C-6 | API | `events` accepted by `include`; one batched query per page; `get_article` always carries events |
| C-8 | Web | Not changed; OpenAPI JSON and generated types refreshed |

Ids C-1…C-8 are the platform's existing ids; no new component is added.

## Key flows

- **F-5 ingest of a slot** — GKG first as today; then for each of Events and Mentions: fetch, md5, publish, mark `published`; a 404 leaves only that file `pending` (diagram 2).
- **F-6 store** — processor → `events.clean` / `mentions.clean` → sink upsert (diagram 2).
- **F-7 read** — `include=events` → page of articles → one query for their events → `events` per article (diagram 2).
- **F-8 retention** — hourly delete by `ingested_at` < now − 7 d on three tables (articles, events, mentions).

## Contracts

Messages (additive; `kind` defaults to `gkg`, so old messages and the GKG path stay valid):

| Message | Topic | Key | Value |
|---|---|---|---|
| `RawMessage` | `gkg.raw` | `slot:row_no` (GKG), `slot:kind:row_no` (others) | `{slot, row_no, line, kind}` |
| `CleanEvent` | `events.clean` | `event_id` | curated fields (spec §5), `source_url_hash` |
| `CleanMention` | `mentions.clean` | `event_id:url_hash` | `event_id, url_hash, url, source_name, mention_time, confidence` |
| `DlqMessage` | `gkg.dlq` | `slot:row_no` | existing fields plus `kind`; reasons `bad_column_count`, `bad_field`, `missing_url`, new `missing_event_id` |

Tables (full DDL in detail):

| Table | Key | Written by | Notes |
|---|---|---|---|
| `events` | `event_id` (bigint) | sink | upsert, newer `date_added` wins; index on `ingested_at` |
| `mentions` | `(event_id, url_hash)` | sink | upsert; index on `url_hash` (the article join) and `ingested_at` |
| `ingest_file` | `(slot, kind)` | ingester | `status`, `attempts`, `row_count` as `ingest_slot` |

API: `include` accepts `tone*` names and `events`. Each article gets `events: [{event_id, date, cameo_code, cameo_root, goldstein, quad_class, num_mentions, num_sources, avg_tone, actor1{code,name,country,type}, actor2{...}, location{name,country,adm1,lat,lon}, source_url, mention_count}]`, at most `api.events_per_article` (20), ordered by `num_mentions` desc.

## Tricky parts

- **Out of order.** No foreign keys (D-5). A mention may precede its event, or point to an event from an earlier slot we never saw; the API returns only events that exist, and an event shows up the next page after it arrives (AC-7).
- **Duplicates inside one slot.** 53 of 2,567 mention rows in the sample repeat an (event, URL) pair, so the mention key is the pair and the write is an upsert (AC-5).
- **Why the join goes through mentions.** In the sample all 996 events have their own `SOURCEURL` among their mentions, so one join covers both "reported by" and "mentioned in" (spec §3). To be re-checked on more slots (open question 3).
- **Independent file state.** `ingest_slot` is keyed by slot alone and is read by `/api/health`; it stays GKG-only, and the new `ingest_file` table holds Events and Mentions state, so GKG can never be blocked (AC-4).
- **Shared topics, single key space.** Non-GKG keys carry the kind so two kinds never share a key; the DLQ key stays `slot:row_no` plus the `kind` field in the value.
- **Update rule.** An event replayed with a newer `date_added` replaces the row; an older one is ignored, so replays are harmless (AC-5, AC-6).

## Failure modes (top)

| Failure | Effect | Handling |
|---|---|---|
| Events or Mentions file 404 / empty | that file stays `pending`, ≤ 4 attempts | GKG unaffected (AC-4) |
| Layout differs from 61/16 columns | rows dead-lettered `bad_column_count` | alert via DLQ count; no partial parse |
| Sink down | consumers stop, no commit | at-least-once replay, idempotent (AC-5) |
| Events table grows past estimate | disk, slower join | measure in AC-14; index on `url_hash`, 7-day delete |

## Technology

No new library or service. `csv`-free tab split like GKG, SQLAlchemy 2 + Alembic 0011, Kafka as today.

## AC coverage

| AC | Component / flow |
|---|---|
| AC-1, AC-2, AC-3 | C-3 (`newsdock_core` parsers, `route`) |
| AC-4 | C-1, F-5 (`ingest_file`) |
| AC-5, AC-6, AC-7 | C-4, C-5 (upserts, no FK), F-6 |
| AC-8 | C-4, C-5, F-8 |
| AC-9, AC-11, AC-12 | C-6, F-7 |
| AC-10, AC-13 | C-6 (`parse_include`, projection at the boundary, ADR-0030) |
| AC-14 | C-1…C-6 on the dev stack (manual) |

## Questions to answer before approving this design

All answered 2026-11-02:

- [x] Reusing `gkg.raw` / `gkg.dlq` for all kinds (a `kind` field decides): accepted (ADR-0032).
- [x] A separate `ingest_file` table, `ingest_slot` and `/api/health` untouched: accepted (ADR-0032).
- [x] An article's events = events it is mentioned in, via `mentions`, at most 20: accepted (ADR-0033).
- [x] The sink consumes three topics in one loop; no back-fill of slots missed before the feature: accepted.
- [x] ADR-0032 and ADR-0033: Accepted 2026-11-02.
