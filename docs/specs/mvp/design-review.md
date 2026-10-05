# mvp — Design review

Reviewed 2026-10-04 · Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Temporary: `/spec-plan` deletes this file once the plan is approved.

## Verdict: **approve with changes**
The design meets every AC on paper and is simple for its learning goals. No blockers. Four majors (sink poison pill, agent throughput/cursor, unapplied `published_at` change, AC-15 healthchecks) and eight minors were found; all are now fixed or accepted with a decision. 3 minors were fixed mechanically, 9 findings were decided by the user.

## Passes

| # | Pass | Result |
|---|---|---|
| 1 | Spec fit | Issues: R-4, R-9. All 15 ACs present once in the coverage table (grep) |
| 2 | Scope | Pass. Nothing from `backlog.md` leaked in; pgvector installed-not-used is within the spec |
| 3 | Simplicity | Pass. Extra hops (processor, sink, Kafka) are justified by the learning goal (ADR-0001/0002, user decisions) |
| 4 | Reality check | Pass. Verified 2026-10-04: `mcp` 2.3.0 and `confluent-kafka` 2.15.1 on PyPI; `apache/kafka` 4.2.2 and `pgvector/pgvector` pg16 images on Docker Hub; Mermaid 11.15.0 on cdnjs. Still unread: `mcp` v2 API (ADR-0003 has a fallback) |
| 5 | Consistency | Issues: R-5, R-6, R-7 (all fixed). Ids, topics, tools, tables match across docs and diagrams |
| 6 | Failure and edge cases | Issues: R-1, R-8, R-12 |
| 7 | Security and data | Pass for a local-only MVP: parameterized SQL, localhost ports, payload escaped, size cap. See R-9 for AC-13 wording |
| 8 | Testability | Issues: R-10, R-11 |
| 9 | ADR hygiene | Issue: R-6 (fixed). Status matches `status.yaml` |
| 10 | Open items | R-2, R-3, R-12 plus the "Design TODOs" in `backlog.md`; all design.md checklist items are ticked |

## Findings

| ID | Sev | Pass | Location | Problem and failure scenario | Suggested fix | Status |
|---|---|---|---|---|---|---|
| R-1 | major | 6 | design-detail §5, §2 Sink | Poison pill at the sink. Only the processor catches bad rows. A row that parses but that Postgres rejects (e.g. NUL byte in a title, out-of-range value) makes the 200-row batch fail, is retried forever without commit, and stalls everything behind it (AC-1…AC-7 stop being true in practice). | On batch failure, retry row by row; send the failing row to `gkg.dlq` with reason `bad_field` (existing reason, no new name); commit. Add to the failure table. | fixed (Decided: row-by-row fallback to DLQ, 2026-10-04) |
| R-2 | major | 6, 10 | design.md F-2, design-detail §2 Cursor, `backlog.md` TODO | Demo agent cannot keep up and its cursor has no home. It scores every new article (~350–530 per slot, 30–50k/day, **[assumption]**) with a local 3–4B model. First run with no cursor takes the last 24 h, so thousands of calls before it catches up. The agent has no DB (AC-13), yet where it persists the cursor is unspecified; losing it re-scores 24 h. | Agent pre-filters (e.g. `search_articles` with `ECON_` / finance themes, ~24% of rows per `research.md`) and caps the first-run window (e.g. 1 h); persist the cursor in a file on a named volume, saved after the batch succeeds. Measure seconds per score in the spike. | fixed (Decided: theme pre-filter, 1 h first-run window, file cursor, 2026-10-04) |
| R-3 | major | 5 | design-detail §2 Processor, design.md §3, spec AC-5, `CLAUDE.md`, `research.md` §4.2 | Known, unapplied change: `published_at` is still column 2 (GDELT processing time), but the real publish time is `<PAGE_PRECISEPUBTIMESTAMP>` (present on 65% of rows, ~1.4 h earlier in the sample). The UI's "newest first", search time filters and AC-5 expectations use the wrong clock. | published_at = precise timestamp when present and parseable, else column 2. Update design.md, design-detail, AC-5 fixture expectations. Retention stays on `ingested_at`. | fixed (Decided: apply precise timestamp, 2026-10-04) |
| R-4 | major | 1 | spec AC-15, design-detail §4 | AC-15 says "all services report healthy" but only kafka, postgres and api have healthchecks; processor, sink, ingester, agent, web have none, so the AC cannot be demonstrated as written. | Define healthchecks for all 8 services (heartbeat file or consumer-group check for workers; HTTP for web) or reword AC-15 to the services that have them. | fixed (Decided: healthchecks for all 8, 2026-10-04) |
| R-5 | minor | 5 | design-detail §2 Processor | Processor algorithm never says where `domain` (col 4) and `gkg_record_id` (col 1) come from, though the `gkg.clean` contract and AC-5 require them. Col 4 confirmed in `research.md` §2. | Add both to the algorithm. | fixed |
| R-6 | minor | 9 | ADR-0002/3/4 | Status "Accepted 2026-10-04" but the body heading said "Decision (proposed)". | Heading → "Decision". | fixed |
| R-7 | minor | 5 | spec.md §3 | Stale: "Kafka and Flink are justified by learning" after D-5/ADR-0001 dropped Flink. | Remove "and Flink". | fixed |
| R-8 | minor | 6 | design.md §4 Slot state, design-detail §2 Ingester | "A 404 never causes a gap" is overstated: only slots seen in `lastupdate.txt` get a row. If the laptop sleeps or compose is down for hours, those slots are never fetched (backfill is out of scope). Also no terminal state after 4 failed attempts (status is only `pending`/`published`). | Add status `failed` after 4 attempts; state in the README that downtime leaves gaps (backfill is backlog). | fixed (Decided: `failed` status + README note, 2026-10-04) |
| R-9 | minor | 1, 7 | spec AC-13, design-detail §4 | AC-13 says the agent reaches data "only via the MCP server", but the agent network includes the API service, which also serves REST `/api/*`. A test can only assert no DB/Kafka route and no credentials. | Reword AC-13 to "no DB or Kafka route and no credentials; data only through the API service", or accept as is. | fixed (Decided: AC-13 reworded, 2026-10-04) |
| R-10 | minor | 8 | AC-3, AC-7 | AC-3 requires re-ingesting an already `published` slot, which the ingester skips by design; AC-7 needs "now" to be controllable. Without hooks the tests are awkward. | Plan note: expose `process_slot(slot, force=True)` and an injectable clock for the retention job. | accepted (Decided: plan note in `backlog.md`, 2026-10-04) |
| R-11 | minor | 8, 10 | spec §8 Assumptions, design.md §6 | Spec says the Ollama model is chosen in design; design says only "~3–4B instruct". AC-14 and R-2 depend on it. | Make choosing and timing the model part of the first spike. | accepted (Decided: first spike, 2026-10-04) |
| R-12 | minor | 6, 10 | `backlog.md` TODO, diagram 5 Check | Open question: an expired URL re-listed by GDELT re-enters (dedup only in Postgres). Cross-slot duplicate rate is unmeasured. | Accept for MVP, measure the duplicate rate over several slots, revisit if material. | accepted (Decided: accept re-entry, measure duplicates, 2026-10-04) |

## What is good (keep)
- One dedup layer (Postgres `PRIMARY KEY` + `ON CONFLICT DO NOTHING`) with a stateless processor and idempotent downstream; this makes AC-3/AC-6 and every crash case simple.
- Cursor = opaque base64 of insert `seq`, not a timestamp: late arrivals are never skipped.
- Retention on `ingested_at` and one API process behind one service layer, with the DB role split and agent network isolation.
