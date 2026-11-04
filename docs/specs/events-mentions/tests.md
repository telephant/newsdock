# Tests — events-mentions

Derived from the ACs in [spec.md](spec.md) §6. Levels: unit (no I/O), integration (Docker: `side_db` Postgres or Kafka scene; never the dev stack's ports, see `CLAUDE.md`), e2e, manual.

## Test data

- **Real samples** (frozen in T-01, 2026-11-02): `packages/core/tests/fixtures/events_sample.tsv` (33 rows of slot `20261102110000`: no actor 1, no actor 2, no geo, old `SQLDATE`, missing lat/long) and `mentions_sample.tsv` (60 rows, starting with a repeated (event, URL) pair). `AvgTone` and `Confidence` were never empty in the real slots checked, so TC-2/TC-4 add hand-made rows for those. `expected_events.json` and `expected_mentions.json` are written by hand in T-02, test-first.
- **Hand-made bad cases** (frozen in T-01): `bad_event_rows.json` (8 cases) and `bad_mention_rows.json` (7 cases: 60/62 and 15/17 columns, empty and non-numeric id, empty URL, bad dates and numbers), like `bad_rows.json` for GKG.
- **Fakes:** the existing fake Kafka/GDELT sources and `side_db` fixture; a fake `GdeltSource` returning per-kind bytes or `None`.
- **Fixture rule:** GDELT fixtures only in `packages/core/tests/fixtures/` (DR rule); the sink, API and ingester tests read them from there.

## Test cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | unit | Given the real rows of `events_sample.tsv`, When `parse_event_row`, Then two hand-checked rows equal `expected_events.json` (ids, dates, actors, CAMEO, Goldstein, counts, tone, geo, `source_url_hash` = `url_hash(source_url)`) and all 33 rows parse with id, CAMEO code, mention count and URL hash equal to their columns |
| TC-2 | AC-1 | unit | Given a row with empty actors, geo and tone, When parsed, Then those fields are `None` and the row is valid |
| TC-3 | AC-2 | unit | Given the real rows of `mentions_sample.tsv`, When `parse_mention_row`, Then the two hand-checked rows equal `expected_mentions.json` (`url_hash` of the normalised URL, mention time, confidence), all 60 rows parse and the repeated pair gives one key |
| TC-4 | AC-2 | unit | Given a mention with empty `Confidence`, When parsed, Then `confidence` is `None` |
| TC-5 | AC-3 | unit | Given each bad row (60 cols, 62 cols, empty/non-numeric id, empty URL, bad date), When parsed, Then a `DlqMessage` with the expected reason (`bad_column_count`, `missing_event_id`, `missing_url`, `bad_field`) and `kind` |
| TC-6 | AC-3 | unit | Given `RawMessage`s of the three kinds (and one without `kind`), When `route`, Then GKG → `gkg.clean` as before, events → `events.clean` keyed by id, mentions → `mentions.clean` keyed `event_id:url_hash`, bad rows → `gkg.dlq` |
| TC-7 | AC-4 | unit | Given a fake source where Events returns `None` and GKG/Mentions return data, When a cycle runs, Then GKG and Mentions rows are published, the `events` file row is `pending` with `attempts = 1`, the GKG slot is `published` |
| TC-8 | AC-4 | unit | Given an Events file failing 4 cycles, Then its status is `failed` and GKG is unaffected; a real `lastupdate.txt` with three lines yields three entries (GKG parse result unchanged) |
| TC-9 | AC-5 | integration | Given stored events and mentions, When the same messages are consumed again, Then both tables' row counts are unchanged |
| TC-10 | AC-5 | integration | Given one batch with the same (event, URL) mention twice and the same event twice, When written, Then no error and one row each |
| TC-11 | AC-6 | integration | Given an event with `num_mentions = 3`, When the same id arrives with `date_added` later and `num_mentions = 7`, Then one row holds 7; an older `date_added` leaves it at 7 |
| TC-12 | AC-7 | integration | Given a mention stored before its event, When the event is stored later, Then the repo returns the event for the article (and nothing before it) |
| TC-13 | AC-8 | integration | Given events and mentions with `ingested_at` older and newer than 7 days, When retention runs, Then only the old rows of both tables are gone and articles retention is unchanged |
| TC-14 | AC-9 | integration | Given an article with two events (mentions stored), When `search`/`list_new`/`get` with `include=events`, Then `events` holds both with curated fields and `mention_count` |
| TC-15 | AC-9 | integration | Given the same data, When MCP `get_article` and `search_articles`/`semantic_search`/`list_new_articles` with `include=["events"]`, Then the same `events` |
| TC-16 | AC-9 | unit | Given an article with 25 events, Then at most 20 return, ordered by `num_mentions` desc then `event_id` |
| TC-17 | AC-10 | integration | Given the same article, When any list/search tool or `GET /api/articles` runs without `include`, or with tone names only, Then no `events` key and the body equals a stored pre-change golden response |
| TC-18 | AC-11 | integration | Given the same article, When `GET /api/articles/{id}` and `GET /api/articles?include=events`, Then both carry `events`; the list without `include` does not |
| TC-19 | AC-12 | integration | Given an article with no event or mention, When returned with `include=events`, Then `events` is `[]` |
| TC-20 | AC-13 | unit+integration | Given `include=bogus` (and `include=events,bogus`), When MCP or REST, Then `invalid_include` / 422 `invalid_include` |
| TC-21 | AC-10, AC-11 | unit | `test_openapi_contract.py`: committed `openapi.json` equals `create_app().openapi()` and documents `events` |
| TC-22 | AC-5…AC-8 | unit | Migration 0011 files pass `test_migration_files.py`; autogenerate against `models.py` is a no-op; grants exist for `ingester_rw`, `sink_rw`, `api_rw` |
| TC-23 | AC-1…AC-4 | unit | `make config-python` green with the new topic names and settings (`fetch_events`, `fetch_mentions`, `events_per_article`) |
| TC-24 | AC-4, AC-5, AC-7, AC-9 | e2e | Fake GDELT with the three fixtures → ingester cycle → processor `route()` → sink writers → API repo, in process on a `side_db` Postgres (`infra/scripts/tests/test_events_pipeline.py`; no Kafka, so it runs next to the dev stack). The Events file is 404 on the first cycle (GKG and Mentions flow, the article has no events), then appears (only it is published, the article returns the event); a replay changes nothing and a later cycle publishes nothing. The Kafka transport of the new topics is covered only by the updated `test_topics.py` and `test_stack.py`, which need the dev stack stopped |
| TC-25 | AC-14 | manual | Checklist below |

## Manual checklist (AC-14, the owner's)

1. `make down`, rebuild images (`make build`), `make up`; confirm `make migrate` applied 0011.
2. Wait for one new slot (about 15–30 min); `ingest_file` shows `events` and `mentions` `published` for it.
3. Run counts: `select count(*) from events; select count(*) from mentions;` and write them in `verify.md`.
4. Pick an article of that slot; `get_article` returns `events` (non-empty), or note why not.
5. Record the share of events whose `source_url_hash` matches an article, and the DLQ count by reason.

## Measurements (provisional targets, not pass/fail)

| ID | What | How |
|---|---|---|
| M-1 | Rows per slot (events, mentions) | count from `ingest_file.row_count` over a day |
| M-2 | Table sizes after 7 days | `pg_total_relation_size('events')`, `('mentions')` |
| M-3 | Share of events with a matching article | join `events.source_url_hash` to `articles.url_hash` |
| M-4 | Extra ingest time per slot | ingester log timestamps for the two extra files |
| M-5 | Latency of `include=events` on a 50-article page | time the repo call vs without `include` |

## AC coverage

Every AC is in the table: AC-1 (TC-1, 2), AC-2 (TC-3, 4), AC-3 (TC-5, 6), AC-4 (TC-7, 8), AC-5 (TC-9, 10), AC-6 (TC-11), AC-7 (TC-12), AC-8 (TC-13), AC-9 (TC-14, 15, 16), AC-10 (TC-17, 21), AC-11 (TC-18, 21), AC-12 (TC-19), AC-13 (TC-20), AC-14 (TC-25). TC-22, 23, 24 are cross-cutting guards.
