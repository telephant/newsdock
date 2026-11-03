# Verify — events-mentions (M3c)

Run 2026-11-02 on branch `agents-whathappen` (worktree `p2-delivery`), nothing committed.

**Verdict: pass with follow-ups, 13 of 14 ACs.** AC-1…AC-13 pass in this run. AC-14 (one real slot on the dev stack, the owner's check) has not been done: it needs `make down`, `make build`, `make up` and `make migrate` on the owner's stack, so `stage` stays `verify` and `gates.verify` stays `pending` until it is run. The follow-ups are F-1…F-4.

## 1. What was run

| Run | Result |
|---|---|
| `make check` (ruff, format, mypy strict, import-linter, layout, config, docs, web lint/format/typecheck/tests, all non-Docker pytest) | exit 0; 846 Python tests passed (437 Docker/rules tests deselected), 182 web tests passed, 5 of 5 import contracts kept |
| Docker modules that use their own throwaway Postgres (`side_db`/`side_postgres`), safe next to the dev stack: `packages/db` schema, ingester file repo, all of `apps/sink/tests/integration`, API events repo/REST/MCP, `infra/scripts/tests/test_events_pipeline.py` | 52 passed in 65 s; no `newsdock-side-*` containers left |
| **Not run** (they need the dev stack stopped): `apps/processor/tests/integration/test_topics.py`, `infra/scripts/tests/test_stack.py` (both updated to five topics), the other Kafka and whole-stack modules that earlier verifies left open | open, see F-3 |

## 2. Acceptance criteria

| AC | Test cases | Result | Evidence (this run) |
|---|---|---|---|
| AC-1 Parse an Events row | TC-1, TC-2 | pass | `packages/core/tests/unit/test_events.py`; also all 996 events of a whole real slot parse (0 dead-lettered) |
| AC-2 Parse a Mentions row | TC-3, TC-4 | pass | `test_mentions.py`; all 2,567 real mentions parse |
| AC-3 Bad rows are dead-lettered | TC-5, TC-6 | pass | `test_events.py`/`test_mentions.py` (15 bad cases), `apps/processor/tests/unit/test_route_kinds.py` |
| AC-4 Independent slot fetch | TC-7, TC-8, TC-24 | pass | `apps/ingester/tests/unit/test_cycle_files.py`; `test_events_pipeline.py` (Events 404 on cycle 1, GKG and Mentions published, Events published alone on cycle 2) |
| AC-5 Replay creates no duplicates | TC-9, TC-10, TC-24 | pass | `apps/sink/tests/integration/test_gdelt_db.py` (Docker); replay in `test_events_pipeline.py` |
| AC-6 Late and updated events | TC-11 | pass | `test_gdelt_db.py::test_newer_event_replaces_and_older_is_ignored` |
| AC-7 Out-of-order mentions are kept | TC-12, TC-24 | pass | `test_gdelt_db.py::test_mention_before_event_is_kept_and_joins_later`; `test_events_repo.py::test_events_become_visible_once_the_event_arrives` |
| AC-8 Retention covers both tables | TC-13 | pass | `apps/sink/tests/integration/test_gdelt_retention.py` |
| AC-9 Events per article through MCP | TC-14, TC-15, TC-16 | pass | `test_events_repo.py`, `test_events_mcp_api.py` (all four list tools, `get_article`, cap and order) |
| AC-10 Payload unchanged without include | TC-17, TC-21 | pass | golden-key tests in `test_events_rest_api.py` and `test_events_mcp_api.py`; `test_openapi_contract.py` |
| AC-11 Events per article through REST | TC-18, TC-21 | pass | `test_events_rest_api.py` |
| AC-12 Article with no events | TC-19 | pass | repo, MCP and REST tests return `[]` |
| AC-13 Invalid include value | TC-20 | pass | MCP `invalid_include` and REST 422 for `bogus`, `events,bogus`, `Events` |
| AC-14 One live slot end to end | TC-25 | **open** | manual, the owner's checklist in `tests.md`; the in-process TC-24 and the whole-slot load in §3 are the closest evidence so far |

TC-22 (migration/models/grants) and TC-23 (config check) also pass (`test_schema.py`, `check_config.py`).

## 3. Measurements (provisional targets, real GDELT data)

Seven real slots were fetched for M-1; one whole slot (`20261102110000`: 962 GKG rows, 996 events, 2,567 mentions) was loaded through the real parsers and sink code into a throwaway Postgres for M-2, M-3 and M-5.

| ID | Measure | Result |
|---|---|---|
| M-1 | Rows per slot | events 735–1,132; mentions 1,982–2,946 (7 slots); 53 repeated mention pairs in the loaded slot (2,567 rows → 2,514) |
| M-2 | Size | per event 518 B with indexes (369 B heap), per mention 574 B with indexes (264 B heap); small tables overstate the index share. Estimate for 7 days: 0.5–0.8 M events (0.2–0.4 GB) and 1.3–2.0 M mentions (0.35–1.1 GB). The spec's first guess (0.7 GB in all) was low. **Not a live 7-day reading** (F-2) |
| M-3 | Events whose source URL has a stored article | 970 of 996 (97.4%) as canonical articles; the other 26 are grouped copies (F-1). Every event and mention URL is stored somewhere (0 not stored) |
| M-4 | Extra ingest time per slot | the Events and Mentions downloads took 0.10 s and 0.13 s against 1.0 s for GKG (curl, slot `…110000`); writing both streams to Postgres took 0.5 s against 4.3 s for the articles |
| M-5 | Latency of `include=events` | page of 50 articles, median of 30 runs: 3.4 ms plain, 5.4–6.3 ms with `events`, 5.4–5.9 ms with tone and events; 71 events on that page, at most 11 per article |

Also seen: 224 of 778 canonical articles in the slot have at least one event; the parsers dead-letter 1 of 962 GKG rows (existing M1 behaviour), none of the Events and Mentions rows.

## 4. Findings

| ID | Finding | Severity | Decision |
|---|---|---|---|
| F-1 | Only the canonical article of a story is in `articles`. Events and mentions whose URL is a grouped copy in `article_sources` do not appear on the canonical: 26 of 996 events and 727 of 2,514 mentions in the sample slot. Only 5 of 778 canonical articles would gain an event through their copies, so the effect is small today. | low | accepted for now; backlog (P2). Recorded in ADR-0033 consequences |
| F-2 | The 7-day table size and the join time at full scale are estimates from one slot. The estimate is above the spec's first guess. | low | read `pg_total_relation_size('events')` / `('mentions')` after a week on the live stack; backlog P3 for trimming (for example `mentions.url`) if it matters |
| F-3 | The Kafka transport of the two new topics is not exercised by any test run so far: TC-24 runs the chain in process. `test_topics.py` and `test_stack.py` were updated but not run, and the earlier whole-stack and Kafka modules are still unrun. | medium | run with the dev stack stopped (`make test-infra SCENE=kafka`, `SCENE=stack`); open, same as the earlier verifies |
| F-4 | GDELT redistribution and attribution terms are still unchecked (`docs/research.md`). No public demo exists. | low | check before any public hosted demo |

Not measured: how often a mention reaches the sink before its event (in the sample, 42% of mentioned events came from earlier slots, which the design already tolerates).

## 5. Doc drift and scope

Fixed in this run: `design-detail.md` §5 (the Kafka loop, not `process_batch`, splits messages by topic; the sink's dead-letter keys and `row_no = -1`; retention is `SqlGdeltWriter.delete_ingested_before`), §7 (ordering in SQL, cap in Python), spec §3 (real volume replaces the guess), ADR-0033 (measured sizes, the grouped-copy consequence). Earlier in the build: hash columns are `text` not `char(64)` (T-04), `fetch_gkg` renamed `fetch` (T-05), OpenAPI twins named `ArticleSummaryEvents` / `FeedPageEvents` (T-09).

Names checked identical across code, docs and tests: topics `events.clean` / `mentions.clean`, tables `events` / `mentions` / `ingest_file`, reason `missing_event_id`, settings `fetch_events` / `fetch_mentions` / `events_per_article`, `include=events`, migration 0011. ADR-0032 and ADR-0033 are Accepted and still accurate. `docs/README.md` still says "ADR-0001 to ADR-0010" (stale before this milestone, not touched).

Scope: 80 changed paths, all in the feature (core parsers and contracts, processor, ingester, sink, db model and migration, API, generated web types and one alias/fixture, config, docs). Nothing from `backlog.md` was implemented (no digest change, no event filters, no web screens, no push on events).

## 6. Next

1. The owner runs the AC-14 checklist (`tests.md`): `make down`, `make build`, `make up`, `make migrate`, wait for one slot, read the counts, call `get_article`. Then re-run `/spec-verify events-mentions` to close it.
2. Run the unrun Docker modules with the dev stack stopped (F-3).
3. The other M3 part, body extraction, has no spec yet (`/spec-init body-extraction`).
