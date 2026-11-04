# Tests — events-grouped-copies

Derived from the ACs in [spec.md](spec.md) §6. Levels: unit (no I/O), integration (Docker: `side_db` Postgres only; never the dev stack's ports, see `CLAUDE.md`), manual.

## Test data

- **Hand-made rows** through the tables and the sink adapters (no new fixture files): a canonical article with one or two copies in `article_sources`, events, and mentions naming the canonical, a copy, or an unknown URL. Helpers exist in `newsdock_db.testing` (`article`) and in the events tests (`_event`).
- **Real evidence** for the shape: events-mentions verify F-1 (26 of 996 events, 727 of 2,514 mentions name a copy in the sample slot). The live measure is in Measurements, not a test.
- **Fakes:** a fake writer implementing the sink ports for the domain tests.
- **Where:** sink tests in `apps/sink/tests/` (`unit/`, `integration/test_mention_links.py`), API tests in `apps/api/tests/integration/test_events_repo.py` and the events MCP/REST modules, migration test in `infra/` next to the existing migration tests.

## Test cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | integration | Given a canonical, a copy and a stored event, When the sink adapter upserts a mention naming the copy, Then a row `(event, canonical)` with `derived = true` exists and the real row is unchanged |
| TC-2 | AC-2 | integration | Given a mention stored for a URL that is not yet a source, When `insert_source` stores that URL as a copy of a canonical, Then the link runs and the derived row exists |
| TC-3 | AC-3 | integration | Given a database at 0012 with mentions naming copies, When `alembic upgrade 0013` runs, Then derived rows exist for them and a second run of the link statement inserts nothing |
| TC-4 | AC-4 | integration | Given an event with 3 real mention rows, one naming a copy (so one derived row), When the canonical is read with `include=events`, Then `mention_count` is 3 |
| TC-5 | AC-4 | integration | Given a derived row for `(event, canonical)`, When a real mention of the canonical arrives with an older `mention_time`, Then the row becomes `derived = false` and counts as real |
| TC-6 | AC-5 | integration | Given the canonical and a copy both mentioned in event 7, When the canonical is read, Then event 7 appears once; two copies of one story mentioning event 8 make one derived row |
| TC-7 | AC-6 | integration | Given a canonical with own and copy events above `events_per_article`, When read, Then the cap holds, ordered by `num_mentions` descending then `event_id` |
| TC-8 | AC-7 | integration | Given the same mentions batch upserted twice, When both runs finish, Then the row counts (real and derived) are equal to one run |
| TC-9 | AC-7 | unit | Given a fake writer, When the mention path runs, Then the link is called once after the upsert; When the source is the canonical's own, Then no link runs; When a copy is stored, Then the link runs once for it, and again when the copy is redelivered (so a lost link heals); no link when the database is down or the batch is empty |
| TC-10 | AC-8 | integration | Given derived and real mentions with `ingested_at` older and newer than the cutoff, When retention runs, Then old rows of both kinds are gone and new ones stay |
| TC-11 | AC-9 | integration | Given the canonical of TC-1, When `get_article`, `GET /api/articles/{id}` and `include=events` on a list and a search are called, Then each carries the copy's event |
| TC-12 | AC-10 | integration | Given the same canonical, When a list or search runs without `include`, Then no `events` key; and an article with no events with `include=events` returns `[]` |

## Coverage

AC-1 TC-1 · AC-2 TC-2 · AC-3 TC-3 · AC-4 TC-4, TC-5 · AC-5 TC-6 · AC-6 TC-7 · AC-7 TC-8, TC-9 · AC-8 TC-10 · AC-9 TC-11 · AC-10 TC-12. All ACs are `auto`; no manual checklist.

## Measurements (provisional, not pass/fail)

| Target (spec §7) | How |
|---|---|
| Backfill time and number of derived rows | read-only count and `EXPLAIN ANALYZE` of the link `SELECT` on the dev database (T-01), then the migration on a copy |
| Storage growth of `mentions` | `pg_total_relation_size('mentions')` before and after on a real slot (assumed up to about 29%) |
| Sink time per mentions batch | time `upsert_mentions` plus the link on a real slot's batch, before and after |
| `include=events` page time | the events-mentions measurement (5.4–6.3 ms per page of 50) repeated after |
