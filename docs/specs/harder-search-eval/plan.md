# Plan — harder-search-eval

## Plan validation (2026-11-04)

| Check | Result |
|---|---|
| AC → test (AC-1…AC-12 each have a TC; TC-1…TC-16 each have an AC) | pass |
| AC → design (`design.md` coverage table) | pass |
| AC → task (table below) | pass |
| Names identical across docs (`derive_clusters`, `collapse`, `check_fixture`, `noise`, `paired_bootstrap`, fixture file names, ADR-0039) | pass |
| No doc treats a Proposed ADR as decided (ADR-0039 Accepted 2026-11-04) | pass |
| Backlog items leaked into scope (body eval, human queries, graded relevance, weighted fusion, CI rebuild) | none |
| Open questions / unchecked items | none |

## Spike first

**T-01** de-risks the biggest unverified claim: that 8 or so consecutive real slots give enough event clusters with different titles (one slot gave 83 events, mostly thin). It fetches the slots and counts, writing the numbers into `design-detail.md` §5. If the count is too low, widen the window before building anything. Note: an earlier fetch returned empty files for some downloads, so the spike also tells how reliable fetching is.

## Tasks (walking skeleton: data → builder → fixture → harness → decision)

| Task | Title | Implements | Depends on |
|---|---|---|---|
| T-01 | Spike: clusters across several real slots | measurements | none |
| T-02 | Builder pure functions (`collapse`, `derive_clusters`, `pick_seeds`, `check_fixture`) | AC-1, AC-2, AC-3, AC-4 | T-01 |
| T-03 | Builder CLI, `make eval-search-build`, build and freeze the fixture | AC-1, AC-3, AC-4 (on real data) | T-02 |
| T-04 | Harness: dataset loader, leave-one-out, noise, bootstrap, sweep | AC-5, AC-6, AC-8, AC-9 | T-03 |
| T-05 | Real-model run, sweep, decision, defaults | AC-7, AC-10, AC-11 | T-04 |
| T-06 | Docs sync and full API suite | AC-12 | T-05 |

Milestones: after T-03 the benchmark exists (AC-1, AC-3, AC-4); after T-04 it runs with a fake embedder (AC-5, AC-6, AC-8, AC-9); after T-05 the numbers and the decision exist (AC-7, AC-10, AC-11).

## Effort

T-01 0.5 h, T-02 2 h, T-03 2 h (mostly waiting on Ollama), T-04 3 h, T-05 1.5 h, T-06 1 h (about one and a half working days) **[assumption]**.

## Definition of Done

Tests first and green (`make test APP=api`, `uv run pytest infra/scripts`, the eval Docker modules); `make check` green; docs and ADR-0039 Result updated in the same edit; no secrets; nothing outside the milestone.
