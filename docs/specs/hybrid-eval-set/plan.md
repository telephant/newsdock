# Plan — hybrid-eval-set

## Plan validation (2026-11-04)

| Check | Result |
|---|---|
| AC → test (AC-1…AC-12 each have a TC; TC-1…TC-12 each have an AC) | pass |
| AC → design (`design.md` coverage table) | pass |
| AC → task (table below) | pass |
| Names identical across docs (`extract_names`, `grade_members`, `build_hard_queries`, `check_hard_fixture`, `without`, `events-hard`, `search_eval_hard_queries.json`, `make eval-search-build-hard`) | pass |
| No doc treats a Proposed ADR as decided (no new ADR; ADR-0039 Accepted and extended) | pass |
| Backlog items leaked into scope (weighted fusion, OR-style keyword leg, NER, bigger corpus, body eval) | none |
| Open questions / unchecked items | none |

## Spike first

**T-01** de-risks the biggest unverified claim: that name-only queries actually make the full-text leg fire. The spec's whole point is a set on which hybrid can differ from vector; if short name queries still give full-text recall near zero, the set would tie again. The spike prototypes the extractor on the frozen seeds, counts the entity queries, and measures the full-text recall of those queries on a throwaway Postgres (no embedder needed). If it is near zero, stop and revisit D-1 before building anything.

## Tasks (walking skeleton: spike → builder → file → harness → decision)

| Task | Title | Implements | Depends on |
|---|---|---|---|
| T-01 | Spike: do entity queries make the full-text leg fire? | measurements | none |
| T-02 | Builder pure functions (`extract_names`, `grade_members`, `build_hard_queries`, `check_hard_fixture`) | AC-1, AC-2, AC-3, AC-4 | T-01 |
| T-03 | Wrapper, `make eval-search-build-hard`, generate and freeze the file | AC-2, AC-4, AC-5 (on real data) | T-02 |
| T-04 | Harness: `ignore`, `without`, dataset `events-hard`, tests | AC-6, AC-7, AC-9 | T-03 |
| T-05 | Real-model run, sweep, decision, ADR Result | AC-8, AC-10, AC-11 | T-04 |
| T-06 | Docs sync, earlier fixtures unchanged, full suites | AC-12 | T-05 |

Milestones: after T-03 the hard set exists (AC-1…AC-5); after T-04 it runs with a fake embedder (AC-6, AC-7, AC-9); after T-05 the numbers and the decision exist (AC-8, AC-10, AC-11).

## Effort

T-01 1 h, T-02 2 h, T-03 1 h, T-04 2 h, T-05 1 h (the sweep takes about two minutes), T-06 1 h (about one working day) **[assumption]**.

## Definition of Done

Tests first and green (`make check-python`, the eval Docker modules, `make config-python`, the whole API suite); docs and the ADR-0039 Result updated in the same edit; no secrets; nothing outside the milestone.
