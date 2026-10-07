# dedup-syndication — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation (2026-10-05)

| # | Check | Method | Result |
|---|---|---|---|
| 1 | AC → test coverage | grep AC column of tests.md | **pass**: AC-1…AC-12 each ≥ 1 TC (14 TCs, no orphans) |
| 2 | AC → design / task coverage | grep design.md §7; `Implements:` in tasks/ | **pass**: 12/12 both |
| 3 | Cross-doc names | grep `story_key`, `article_sources`, `source_count`, `sources`, `NEWSDOCK_STORY_WINDOW_HOURS` across spec/design/tests/tasks | **pass** |
| 4 | Proposed ADRs treated as decided | grep Status in ADR-0011/0012 | **pass**: both Accepted 2026-10-05 |
| 5 | Untagged claims / invented numbers | review | **pass**: 14 % measured; 48 h and 25/45 are config/constants decided in ADR-0012, not ACs |
| 6 | Scope leaks from backlog.md | grep fuzzy/embedding/backfill/canonical-quality in tasks | **pass**: only under "Out of scope" |
| 7 | Open questions / checklist items | grep `- [ ]` | **pass**: none |

**Verdict: GO.** `gates.plan: approved`. No design-review.md exists for this feature, so nothing to retire.

## Spike first

**T-01** implements the pure story keyer *and calibrates it against reality in the same half-day*: the riskiest claim is that the 25/45 thresholds + 48 h window group the measured 14 % without false merges. The calibration script runs `story_key` over the two saved live slots (527 + 1208 rows), records grouping %, the max published_at spread per group, and a hand-checkable list of every multi-copy group; findings land in this file under Progress.

**Progress:** T-01 ✅ 2026-10-05 — `newsdock_core.stories.story_key` (TC-1, 32 core tests green). Calibration on the two saved live slots: 527 articles → 437 stories (17.1 % copies grouped) and 1208 → 1028 (14.9 %); max published_at spread within a group **13.7 h** (window 48 h validated); top-20 multi-copy groups hand-checked — all genuine syndication (ACM/Newsquest/iHeart/NPR networks), **0 false merges**. ADR-0012 thresholds confirmed unchanged. T-02 ✅ 2026-10-05 — `Article.story_key` + `ArticleSource` models, Alembic 0003 (no backfill, grants); drift test failed-then-passed, `SCENE=db` green. T-03 ✅ 2026-10-05 — sink grouping (StoryWriter port: window lookup, in-batch cache, own-source heal, per-article poison fallback, AC-12 log); TC-13, TC-14 unit + TC-2…TC-5, TC-12 docker green; M1 suite intact. T-04 ✅ 2026-10-05 — API: `source_count` on summaries (grouped COUNT per page, NULL-key fallback 1), `sources[]` + `source_count` on the detail, OpenAPI/types regenerated; TC-6, TC-7, TC-8 green (`SCENE=api`), TC-9 green (in infra/scripts/tests, cross-app; added to `SCENE=pipeline`). T-05 ✅ 2026-10-05 — UI: `· N sites` badge (only when > 1) and a "Seen on N sites" sources section with escaped links; TC-11 green (5 web tests, RTL cleanup added).

## Tasks

| Phase | Task | Title | ACs | Effort |
|---|---|---|---|---|
| P0 | T-01 | Story keyer in core + live-slot calibration | 1 | 0.5 d |
| P1 | T-02 | Schema: `story_key`, `article_sources`, Alembic 0003 | (enables 2–8, 11) | 0.5 d |
| | T-03 | Sink grouping: window lookup, in-batch cache, dedup log | 2, 3, 4, 5, 11, 12 | 1 d |
| P2 | T-04 | API: `source_count` + `sources[]` (+ regenerated web types) | 6, 7, 8, 9 | 0.5 d |
| | T-05 | UI: "N sites" badge + sources list | 10 | 0.5 d |

**Milestone markers:** after T-03 → stories grouped in the store on real data (AC-2…AC-5, AC-11, AC-12). After T-05 → visible end-to-end, ready for `/spec-verify` (AC-6…AC-10). Total ≈ 3 working days.

## Definition of Done (every task)

1. Tests named in the task written **first** and green (`make test APP=…`; docker-marked via `make test-infra SCENE=…`).
2. `make check` green; CI green if pushed.
3. Docs updated in the same change when a fact moves (design/detail, CLAUDE.md fixed names gain `article_sources`, `story_key`, `source_count`).
4. No secrets; `.env.example` untouched (the window var has a code default).

Out of scope: everything in [backlog.md](backlog.md) (canonical-quality ranking, fuzzy/embedding grouping, backfill/regroup, merge repair, cross-language).
