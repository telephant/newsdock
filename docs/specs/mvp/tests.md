# mvp — Tests

Spec: [spec.md](spec.md) §6 · Design: [design.md](design.md) · Derived 2026-10-05.

## Test data and fakes

- **Real GKG fixture**: ~20 rows cut from slot `20261004081500` (verified in `docs/research.md`), with expected values in `expected_articles.json`. Must include: a row with `<PAGE_PRECISEPUBTIMESTAMP>`, a row without (col-2 fallback), rows with empty themes/persons/orgs, an empty `domain` had no real example in the slot, so it is a synthetic variant of a real line (in `bad_rows.json`). Lives in `packages/core/tests/fixtures/` (`gkg_sample.tsv`, `expected_articles.json`, `bad_rows.json`), created in T-02.
- **Hand-made bad rows** (same folder): missing URL, missing title, 26 and 28 columns, a >2 KB line, a NUL-byte title (sink poison).
- **Fakes**: GDELT HTTP → local fake server (`pytest-httpserver`): serves `lastupdate.txt`, zips, 404s, md5 mismatches. Ollama → faked HTTP returning structured JSON. Clock → injected into the retention job. Kafka and Postgres are **not** faked at integration level: those tests run against the compose broker/DB and are marked `docker` (convention from M0, `make test-infra`).
- **Levels**: unit = no container needed; integration = marked `docker`; e2e/manual = live feed, run at `/spec-verify`.

## Test cases

| TC | AC | Level | Given / When / Then |
|---|---|---|---|
| TC-1 | AC-1 | unit | Given a fixture slot zip on the fake server, when the ingester processes the slot, then exactly one `gkg.raw` message per TSV row is produced (fake producer), keyed `<slot>:<row_no>`, and the slot becomes `published` only after flush |
| TC-2 | AC-1 | integration | Same slot against real Kafka: consumer reads back exactly N messages from `gkg.raw` |
| TC-3 | AC-2 | unit | Given the GKG URL returns 404 or an empty body, when the ingester polls, then nothing is published, the event is logged, the slot stays `pending` with attempts+1, no crash |
| TC-4 | AC-2 | unit | Given an md5 mismatch vs the index line, then handled exactly like a 404 (retry later) |
| TC-5 | AC-2 | unit | Given a slot with 3 failed attempts, when the 4th fails, then status `failed`, logged, excluded from further retries |
| TC-6 | AC-3 | integration | Given a slot already ingested and stored, when re-ingested via `process_slot(slot, force=True)` (test hook, R-10), then the article count is unchanged |
| TC-7 | AC-4 | unit | Given a row with no URL / no title, when parsed, then routed to dlq with reason `missing_url` / `missing_title` |
| TC-8 | AC-4 | unit | Given a row with ≠ 27 columns, then dlq `bad_column_count`; the dlq message's `line` is truncated to ≤ 2 KB |
| TC-9 | AC-4 | integration | A bad row sent through the running processor lands on `gkg.dlq` with `{reason, slot, row_no, line, at}` |
| TC-10 | AC-5 | unit | The ~20-row real fixture parses to the expected title, url, url_hash, domain, published_at (precise timestamp when present, else col 2), themes, persons, orgs, tone |
| TC-11 | AC-5 | unit | Empty themes/persons/orgs parse as `[]` and are **not** dead-lettered; empty domain → null |
| TC-12 | AC-6 | integration | Two rows with the same normalized URL in different slots: the store holds one article |
| TC-13 | AC-7 | unit | With an injected clock (R-10), articles aged 8 d are deleted, 6 d kept |
| TC-14 | AC-7 | unit | Deleting an article cascades to its analyses |
| TC-15 | AC-8 | integration | An MCP client lists exactly `search_articles`, `get_article`, `list_new_articles`, `submit_analysis` |
| TC-16 | AC-9 | integration | Stored articles with varied time/theme/domain/title: combined filters return only matches, at most `limit` |
| TC-17 | AC-9 | unit | `text` filter escapes `%` and `_` (no ILIKE wildcard injection) |
| TC-18 | AC-9 | unit | `limit` clamped: default 20 / max 100 (search), default 50 / max 200 (list_new) |
| TC-19 | AC-10 | integration | Calling `list_new_articles` again with the returned cursor before any new data → empty list, same-or-newer cursor |
| TC-20 | AC-10 | unit | No cursor → only articles with `ingested_at` ≥ now − `FIRST_RUN_WINDOW` (1 h) |
| TC-21 | AC-11 | integration | `submit_analysis(article_id, agent_name, payload)` → `get_article` returns that analysis |
| TC-22 | AC-11 | unit | Unknown `article_id` → MCP error `not_found` (FK violation mapped) |
| TC-23 | AC-11 | unit | Payload > 64 KB rejected |
| TC-24 | AC-11 | unit | Resubmission by the same (article, agent) replaces the payload (latest wins) |
| TC-25 | AC-12 | manual | Checklist: feed shows articles newest-first (`published_at`); theme filter narrows the list; agent score visible where present; detail view shows analyses |
| TC-26 | AC-12 | unit (web) | Feed component renders fixture articles; `payload.reason` renders as escaped text, never HTML (XSS) |
| TC-27 | AC-13 | integration | The running `agent` container holds no DB/Kafka env vars; a connection attempt to `postgres:5432` and `kafka:9092` from it fails (no route); it reaches `api` |
| TC-28 | AC-14 | auto | `python -m agent.eval --labels labels.csv` on ≥ 50 labelled rows prints precision, recall, F1 and confusion counts |
| TC-29 | AC-14 | unit | Ollama structured output parses to `{relevant, score (0–1), reason}`; malformed output → logged and skipped, no crash |
| TC-30 | AC-15 | manual | Checklist: clean clone → `.env` from example → `make up` + apps profile (spec says `docker compose up`; `make up` wraps it, noted in README) → one live poll cycle → all 8 services healthy → UI lists ≥ 1 real article |
| TC-31 | AC-4 | unit | Sink batch insert fails → row-by-row retry; the poison row (NUL title) → `gkg.dlq` reason `bad_field`; remaining rows written; offsets committed. A connection error instead → no commit, backoff (R-1) |
| TC-32 | AC-10 | unit | Agent saves the cursor file only after the whole batch succeeded; a crash mid-batch keeps the old cursor (R-2) |
| TC-33 | AC-15 | integration | Worker heartbeat healthcheck: fresh `/tmp/healthy` mtime → healthy; stale (> 2× loop interval) → unhealthy (R-4) |
| TC-34 | AC-5 | unit | Alembic autogenerate against the ORM metadata is a no-op (schema and migrations in step, R-14) |
| TC-35 | AC-13 | unit | Agent config exposes only `MCP_URL` and `OLLAMA_URL`; constructing it with a DSN-style var fails validation |

Coverage: every AC-1…AC-15 has ≥ 1 TC; no TC without an AC (validated in plan.md).

## Manual checklists

- **AC-12 (TC-25)** and **AC-15 (TC-30)** run at `/spec-verify` on the owner's machine against the live feed; steps as written in the TC rows above.

## Measurements (provisional targets from spec §6 — recorded, not pass/fail)

| What | Target (guess) | Measured (T-11 live run, 2026-10-05) |
|---|---|---|
| E2E latency: slot fetched → article in UI | < 2 min | **seconds** once the file is fetchable (12,100-msg replay drained in <5 s). GDELT's own publish lag + the 15-min poll cycle dominate: the live slot 404'd on cycle 1 (documented quirk) and was published on cycle 2 (1317 rows) |
| Demo agent F1 on labelled set | ≥ 0.7 | **0.83** (precision 0.83, recall 0.83; [labels.csv](labels.csv): 100 rows, 30 positive, threshold 0.5, llama3.2:3b). The first terse prompt scored F1 0.06 — a rubric + 3 few-shot examples fixed it (2026-10-05) |
| Throughput headroom | ≥ 10× observed rate | **far exceeded**: 10× replay of a 1210-row slot (12,100 msgs) drained end-to-end in < 5 s (≳ 2400 msg/s vs ~1.3 msg/s feed rate) |
| Whole stack RAM | ≤ 8 GB | **~1.07 GiB** total, 8 services (`docker stats`; Kafka JVM 672 MiB is the largest) |
| Seconds per agent score | informs R-2 | 1.37 s mean / 1.82 s p95 (llama3.2:3b, T-01 spike), confirmed live |
| Cross-slot duplicate rate | unknown (R-12) | 0 duplicates between the 2 observed slots (13:15 replay + live 14:15); rate over ≥ 4 consecutive slots still to measure during the /spec-verify soak |
