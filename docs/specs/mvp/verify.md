# mvp — Verification

Run 2026-10-05 · Spec: [spec.md](spec.md) · Tests: [tests.md](tests.md) · Verdict: **pass with follow-ups**

## 1. Full runs (this session, real output)

| Command | Result |
|---|---|
| `make check` | **green** — Python `145 passed, 66 deselected`; web `3 passed`; ruff lint+format, mypy strict (0 issues, 91+ files), import-linter `3 kept, 0 broken`, layout, docs-check all passed |
| `make test-infra` | **green** — `46 passed, 165 deselected in 231.58s` (all docker-marked: schema/cascade, Kafka publish, processor pipeline, sink dedup/retention/poison, re-ingest, MCP API, agent isolation, full 8-service stack, images, M0 stack) |

## 2. AC results

| AC | TC(s) | Result | Evidence |
|---|---|---|---|
| AC-1 ingest slot | TC-1, TC-2 | **pass** | unit + real-Kafka round-trip in this run; live: slot `20261005141500` published 1317 rows |
| AC-2 retry 404 | TC-3, TC-4, TC-5 | **pass** | unit in this run; live: newest slot 404'd, retried, published on cycle 2 (ingester logs) |
| AC-3 re-ingest idempotent | TC-6 | **pass** | `test_reingest.py` (force hook, count unchanged) in this run |
| AC-4 dead-letter | TC-7, TC-8, TC-9, TC-31 | **pass** | parse reasons + live dlq message + sink poison fallback, all in this run |
| AC-5 field extraction | TC-10, TC-11, TC-34 | **pass** | 20 real rows vs expected values; autogenerate no-op |
| AC-6 cross-slot dedup | TC-12 | **pass** | one row for same URL in two slots |
| AC-7 7-day retention | TC-13, TC-14 | **pass** | injected clock: 8 d gone, 6 d kept; cascade |
| AC-8 MCP tool list | TC-15 | **pass** | client sees exactly the 4 designed tools |
| AC-9 search filters | TC-16, TC-17, TC-18 | **pass** | combined filters, ILIKE escaping (`5%` matched literally), clamps |
| AC-10 cursor | TC-19, TC-20, TC-32 | **pass** | same cursor back on no-new-data; 1 h first-run window; cursor saved only after batch |
| AC-11 write-back | TC-21…TC-24 | **pass** | submit → get round-trip; resubmit replaces; not_found; 64 KB cap |
| AC-12 UI feed | TC-26, TC-25 | **pass (manual-ok)** | TC-26 green; TC-25 confirmed by the owner 2026-10-05 (after the CORS fix) |
| AC-13 agent isolation | TC-27, TC-35 | **pass** | no DB/Kafka env or route from the agent container; api reachable; config forbids extras |
| AC-14 agent eval | TC-28, TC-29 | **pass** | eval ran on 100 labelled rows (model pre-filled, owner-reviewed): precision 0.83, recall 0.83, **F1 0.83** ([labels.csv](labels.csv)) |
| AC-15 end-to-end | TC-33, TC-30 | **pass (manual-ok)** | TC-33 + all-8-healthy green on a fresh-volume live stack; owner accepted this run as TC-30 (2026-10-05) |

## 3. Measurements (live run, 2026-10-05 — details in tests.md)

RAM **~1.07 GiB** (target ≤ 8 GB) · throughput **≳ 2400 msg/s** vs ~1.3 msg/s feed (≥ 10× met) · pipeline latency **seconds** once a slot is fetchable (GDELT publish lag + 15-min poll dominate) · 1.37 s/score (llama3.2:3b) · cross-slot duplicates 0/2 slots (rate over ≥ 4 slots: follow-up) · agent F1 **0.83** on 100 labelled rows (the first terse prompt scored 0.06; fixed with a rubric + few-shot examples — small local models need explicit criteria)

## 4. Doc drift

- **None open.** Greps: MCP tool names, topics, dlq reasons, tables, REST routes, slot statuses, CleanArticle fields all match design.md §3 / design-detail §1. pgvector: extension only, no vector columns. No backlog feature leaked into code.
- Fixed during implementation/verify (recorded where found): design-detail §1 identity/index/roles wording (T-03); `AGENT_THEME_PREFIXES` default `ECON_` only (T-01 spike, user decision); MCP transport Host allowlist 421 gotcha (T-11, design-detail §4); three stale M0 tests updated for M1 reality (empty metadata, `alembic_version=0002`, image default command → entrypoint import); **CORS missing on `/api/*`** — found by the owner in the browser during TC-25 (curl and stubbed-fetch tests can't see CORS): CORSMiddleware added, GET-only, UI origins only, with `test_cors.py` as regression (2026-10-05).

## 5. Manual checklists (owner)

- **TC-25 (AC-12):** confirmed ok by the owner 2026-10-05 (feed order, theme filter, score badges, detail view). Found and fixed on the way: missing CORS on `/api/*`.
- **TC-30 (AC-15):** owner accepted this session's fresh-volume live run (live GDELT slot ingested after the documented 404 retry, 8/8 healthy, UI shows real articles) as the end-to-end check, 2026-10-05.
- **AC-14 F1:** done 2026-10-05 — `docs/specs/mvp/labels.csv` (100 rows, model pre-filled, owner-reviewed), F1 0.83.

## Verdict

**Pass with follow-ups.** All 15 ACs pass (13 automated in this session's runs; AC-12 and AC-15 manual-ok by the owner). Follow-ups moved to backlog.md: cross-slot duplicate-rate soak over ≥ 4 consecutive live slots (R-12), optional clamp of future `published_at` values (bogus publisher timestamps pin articles to the feed top), docker-test parallelization (P3). Provisional targets all met or exceeded: F1 0.83 (≥ 0.7), RAM 1.07 GiB (≤ 8 GB), throughput ≫ 10×.
