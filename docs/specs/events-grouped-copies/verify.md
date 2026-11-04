# Verify — events-grouped-copies (M3e)

Run 2026-11-04. **Verdict: pass with follow-ups, all 10 ACs.** The live readings on the real dev stack are still open (F-1); the synthetic-scale numbers below are first readings only.

## 1. Runs

| Run | Result |
|---|---|
| `make check-python` (ruff, mypy strict, import-linter, layout, config, unit tests) | 1,150 passed, 524 Docker-marked deselected |
| Whole API suite incl. Docker modules (`pytest apps/api -m "docker or not docker"`) | 837 passed |
| Whole sink suite incl. Docker modules | 56 passed |
| The 65 tests mapped to the ACs below, run together again at verify | 65 passed |
| `make test-infra SCENE=e2e` (dev stack stopped; it rebuilt the sink, api and migrate images from this worktree, so migration 0013 ran in the compose stack) | 11 passed |
| `make test-infra SCENE=pipeline` | 2 passed |
| `make docs-check` | clean |

## 2. Acceptance criteria

| AC | TC | Result | Evidence |
|---|---|---|---|
| AC-1 | TC-1 | pass | `test_a_mention_of_a_copy_gets_a_derived_row_for_the_canonical` |
| AC-2 | TC-2 | pass | `test_a_copy_grouped_after_its_mention_links_the_stored_mentions` |
| AC-3 | TC-3 | pass | `test_migration_0013_backfills_derived_rows_once_and_is_repeatable`, `test_orm_model_matches_migration_0013` |
| AC-4 | TC-4, TC-5 | pass | `test_mention_count_counts_real_mentions_only`, `test_a_real_mention_of_the_canonical_beats_the_derived_row`; MCP and REST variants |
| AC-5 | TC-6 | pass | `test_an_event_of_the_canonical_and_its_copy_appears_once`, `test_two_copies_and_the_canonical_make_one_row_per_event` |
| AC-6 | TC-7 | pass | `test_events_found_through_copies_are_capped_and_ordered` |
| AC-7 | TC-8, TC-9 | pass | `test_replaying_a_batch_changes_nothing`, the four wiring unit tests |
| AC-8 | TC-10 | pass | `test_retention_removes_derived_and_real_rows_together` |
| AC-9 | TC-11 | pass | `test_the_detail_carries_them_too`, REST and MCP `test_event_of_a_copy_shows_on_the_canonical_with_real_mention_count` |
| AC-10 | TC-12 | pass | the existing events REST/MCP/repo tests (no `events` key without `include`, `[]` when none) still pass with the new fixtures |

## 3. Measurements (synthetic, throwaway Postgres; not the real stack)

The dev database was not running, so these use generated data shaped like the F-1 sample: 60,000 stories each with one copy, 340,000 real mentions of which about 29% name a copy.

| Target | Reading |
|---|---|
| Derived rows created | 87,000 on 340,000 real rows = 25.6% (assumption was up to about 29%) |
| `mentions` size with indexes | 54.5 MB → 72.2 MB (+32%) |
| Backfill statement | 0.35 s for the whole table |
| One slot's batch of 2,500 mentions (29% naming copies) | upsert 0.17 s, link 0.53 s, a repeat of the link 0.54 s |
| `include=events` page of 50 articles | inconclusive: 12.5–25.7 ms with derived rows, 5.7–45.7 ms without (noise larger than the effect) |

Reading: the link costs about three times the upsert, roughly half a second per 15-minute slot, which is small. Storage grows by a third, in line with the assumption. The page-time effect is not measurable at this noise. At the 7-day size the growth would be about 0.4–0.6 M extra rows **[assumption, scaled from the sample]**.

## 4. Drift and scope

- Fixed during verify: `design-detail.md` §1 still described a downgrade (migration is forward-only, DR-11); `design.md` and the sequence diagram said "new copy" (the link now runs on every copy, T-04 refinement).
- Names are identical across code and docs (`derived`, `link_copy_mentions`, `link_mentions_of`, migration `0013`, ADR-0038). ADR-0038 and ADR-0033's amended consequence match the code.
- Scope: nothing from `backlog.md` was implemented; no new API argument, no web or digest change.

## 5. Follow-ups

| ID | Priority | Finding | Decision |
|---|---|---|---|
| F-1 | P2 | No reading on the real dev stack: backfill time, `pg_total_relation_size('mentions')` before and after, and the count of canonicals that gained events | owner: after `make build`, `make migrate` (0013) and `make up`, read them (queries in §3); record here |
| F-2 | P3 | `include=events` page time effect not measurable in the synthetic run | re-read on the live stack together with F-1 |
| F-3 | P3 | A story merge that moved a copy to another canonical would leave stale derived rows; `insert_source` never moves a copy today, so it cannot happen | accepted; revisit if regrouping is ever added |
| F-4 | P3 | The Kafka-transport scenes `kafka` and `stack` were not re-run for this change (it touches no topic or contract; `e2e` and `pipeline` ran) | run `make test-infra` with the dev stack stopped before the next release |
