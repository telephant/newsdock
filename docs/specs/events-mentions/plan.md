# Plan — events-mentions

Spec [spec.md](spec.md) · design [design.md](design.md) · tests [tests.md](tests.md). Implement one task at a time with `/spec-implement events-mentions T-NN`, tests first.

## Plan validation

Run 2026-11-02 with grep over the spec folder.

| # | Check | Result |
|---|---|---|
| 1 | Every AC (1…14) has at least one test in `tests.md`; every cited TC exists; all 25 TCs are used by a task | pass |
| 2 | Every AC appears in `design.md` and in at least one task | pass |
| 3 | Names consistent across spec, design, diagrams, tests, tasks: topics `events.clean`, `mentions.clean`; tables `events`, `mentions`, `ingest_file`; settings `fetch_events`, `fetch_mentions`, `events_per_article`; reason `missing_event_id`; `include=events` | pass |
| 4 | No doc treats a Proposed ADR as decided: ADR-0032 and ADR-0033 are Accepted 2026-11-02; no "Proposed" left in the folder | pass |
| 5 | Untagged claims, invented numbers, glossary | fixed: the spec flow now says "mentioned in" (matches ADR-0033); `kind` and `ingest_file` added to the glossary; the 6-day effort is tagged **[assumption]**; the 20-event cap and the 7-day window are decisions, not measurements |
| 6 | Backlog items leaked into scope | none (digest, filters, push, UI, extra columns, body extraction stay out) |
| 7 | Open questions and unchecked checklist items | none: design checklist all ticked; no back-fill decided |

Open risks carried into implementation (not blockers):

- R-1 (closed 2026-11-02) Column map re-checked on six slots by T-01; confirmed.
- R-2 (low) Table size and join time are estimates from one slot; measured in AC-14 and M-2/M-5.
- R-3 (low) `gkg.raw` and `gkg.dlq` carry non-GKG lines (ADR-0032 consequence).
- R-4 (low) Docker scenes (TC-9…TC-13, TC-24) need the dev stack stopped.

Go: next step `/spec-implement events-mentions T-01`.

## Spike first

**T-01** de-risks the biggest unverified claim: the column maps (confirmed on one sample row and two slots' column counts only) and the join/fan-out numbers (one slot). It freezes the fixtures every later task reads. If the layout differs from the design, change the design before any code.

## Tasks (order = dependency order; walking skeleton marker after T-06)

| Task | Title | AC | Depends on |
|---|---|---|---|
| T-01 ✅ 2026-11-02 | Spike: verify layout on more slots, freeze fixtures | prerequisite of AC-1…3 | none |
| T-02 ✅ 2026-11-02 | Core contracts and parsers (`kind`, `CleanEvent`, `CleanMention`, `missing_event_id`) | AC-1, AC-2, AC-3 | T-01 |
| T-03 ✅ 2026-11-02 | Processor routing by `kind`, new topics and settings | AC-3 | T-02 |
| T-04 ✅ 2026-11-02 | Migration 0011, models, grants | AC-5…AC-8 (schema) | T-02 |
| T-05 ✅ 2026-11-02 | Ingester: three files per slot, `ingest_file`, `kind` on messages | AC-4 | T-02, T-04 |
| T-06 ✅ 2026-11-02 | Sink: events and mentions writers, three-topic loop | AC-5, AC-6, AC-7 | T-03, T-04 |
| T-07 ✅ 2026-11-02 | Sink retention for both tables | AC-8 | T-06 |
| T-08 ✅ 2026-11-02 | API domain and repo: `events` in `include`, events query, detail | AC-9, AC-10, AC-12, AC-13 | T-04 |
| T-09 ✅ 2026-11-02 | API surfaces: MCP, REST, OpenAPI, web types | AC-10, AC-11, AC-13 | T-08 |
| T-10 ✅ 2026-11-02 | Pipeline e2e, docs, CLAUDE.md, live check | AC-4, AC-5, AC-9, AC-14 | T-05, T-06, T-07, T-09 |

**Milestones:** after T-06 the pipeline stores events and mentions from fixtures (AC-1…AC-3, AC-5…AC-7); after T-09 agents read them (AC-9…AC-13); after T-10 AC-4 is also proven end to end and AC-14 is the owner's check.

T-04 and T-08 can run in parallel with T-03 and T-05 once T-02 is done; the list is sequential only for clarity.

## Effort (rough)

Spike 0.5 d · core + processor 1 d · migration + ingester 1 d · sink 1 d · API + surfaces 1.5 d · e2e, docs, live 1 d. About 6 days of focused work **[assumption]**.

## Definition of Done (every task)

- Tests listed in the task written first and green; related existing tests still green.
- `make check` green for the touched apps (`make test APP=<app>`), `make config-python` after config changes.
- Docker tests only with the dev stack stopped (`make down`), never on ports 5433/29092 with it running.
- Docs updated in the same edit where a fact repeats (`CLAUDE.md` fixed names, topics, tables; ADRs); `status.yaml` ACs updated.
- No secrets; SQL parameterised; no scraping.

## Out of scope (stays in `backlog.md`)

Digest agent change, UI screens, event filters, push on events, extra Events columns, body extraction.
