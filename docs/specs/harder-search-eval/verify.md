# Verify — harder-search-eval (M3f)

Run 2026-11-04. **Verdict: pass with follow-ups, all 13 ACs.** The eval now separates keyword and full-text search from vector search and every default was kept on the numbers. It cannot yet separate vector from hybrid or tell `semantic_rrf_k` and `semantic_candidates` apart (F-1).

## 1. Runs

| Run | Result |
|---|---|
| `make check-python` (ruff, mypy strict, import-linter, layout, config, unit tests) | 1,191 passed, 528 Docker-marked deselected |
| Whole API suite incl. Docker modules and the real-model eval tests | 852 passed (837 before this milestone) |
| `make docs-check`, `make config-python` | clean |
| `make eval-search` (real model `nomic-embed-text`, both datasets, prefixes on and off) | 1 passed in 46 s |
| `make eval-search-sweep` (real model, 24 rows) | 1 passed in 117 s |
| `make eval-search-build` twice from the same cached slots and model | byte-identical files (`shasum` equal, git tree clean) |

## 2. Acceptance criteria

| AC | TC | Result | Evidence |
|---|---|---|---|
| AC-1 | TC-1 | pass | `test_the_frozen_fixture_passes_the_builders_rules`, `test_the_fixture_is_big_enough_to_discriminate_and_has_both_kinds` |
| AC-2 | TC-2, TC-3 | pass | `test_clusters_are_exactly_the_articles_of_one_event`, `test_an_event_mentioned_only_by_copies_makes_no_cluster` and the repeated-mention case |
| AC-3 | TC-4 | pass | `test_a_query_that_is_empty_or_a_title_is_rejected` (5 cases); the frozen queries pass `check_fixture` |
| AC-4 | TC-5 | pass | `test_expected_ids_must_be_the_cluster_without_the_seed` (5 cases); the frozen fixture passes |
| AC-5 | TC-6, TC-7 | pass | `test_the_events_eval_prints_overall_by_kind_and_noise`, `test_the_seed_is_removed_before_scoring_and_the_list_is_cut_to_k` |
| AC-6 | TC-8, TC-12 | pass | `test_the_sweep_has_one_row_per_combination` (24 rows), the paired-bootstrap unit tests and `clear_win` |
| AC-7 | TC-13 | manual-ok | real model, events set: keyword 0.000, full-text 0.103, vector 0.764 recall@5 (§3) |
| AC-8 | TC-9, TC-10 | pass | `test_noise_counts_relevant_vector_hits_that_hybrid_dropped`; the noise line is printed |
| AC-9 | TC-11 | pass | `test_two_runs_print_identical_numbers`; the fixture rebuild is byte-identical |
| AC-10 | TC-14 | manual-ok | ADR-0039 "Result": prefix kept, `semantic_rrf_k` kept at 60, `semantic_candidates` kept at 50, with the numbers |
| AC-11 | TC-15 | pass | `make config-python` clean (no default changed) |
| AC-12 | TC-16 | pass | whole API suite 852 passed, no change under `apps/*/src` (`git diff --stat` since spec-init: tests, scripts, fixtures, Makefile, `pyproject.toml` only) |
| AC-13 | TC-17 | pass | `test_a_member_the_judge_rejects_leaves_expected_but_stays_in_the_corpus`, `test_a_cluster_with_no_verified_member_makes_no_queries`, `test_a_rejected_near_duplicate_is_left_out_of_the_corpus_not_made_a_negative` |

## 3. Measurements (real data, real model)

| Target (spec §7) | Reading |
|---|---|
| Method scores, events set (146 queries, 1,557 articles), prefixes on | keyword 0.000 / 0.000, full-text 0.103 / 0.099, vector 0.764 / 0.660, hybrid 0.764 / 0.660 (recall@5 / MRR); by kind: keywords vector 0.77, paraphrase 0.76 |
| Method scores, prefixes off | vector 0.768 / 0.645, hybrid 0.765 / 0.651 |
| Hybrid noise | of 120 relevant vector top-5 hits hybrid dropped 0 (1 of 121 without prefixes); of 16 relevant full-text hits it dropped 0 |
| Sweep | 24 rows identical across `rrf_k` and `candidates`; 0 clear wins over the defaults |
| Clusters and queries | 8 slots: 580 candidate clusters, 1,119 judged pairs, judge said yes to 95 (8.5%), 73 clusters, 146 queries (73 paraphrase, 73 keywords) |
| Fixture size | 469 KB corpus + 61 KB queries (a little above "a few hundred KB") |
| Run time | `make eval-search` 46 s, sweep 117 s, rebuild about 2 minutes |
| Builder determinism | identical files on a second build |
| Query quality (20 read) | most plausible searches; a few paraphrases drift from the facts (for example a wrong year); judge log read: yes answers were the same story, random no answers unrelated, wrong refusals were near-duplicate headlines (handled by the ambiguity rule) |

## 4. Drift and scope

- Fixed: the design named the support module `harness.py`; it is `search_eval_harness.py`, and the pytest `pythonpath` and mypy `mypy_path` entries it needs are in the root `pyproject.toml` (recorded in `tasks/T-04.md`).
- Decided and recorded during the work: D-1 amended after measuring noisy GDELT event links (a local-model judge, ADR-0039), the ambiguity rule, one cluster per seed and one query text per kind (design-detail §1 steps 3b, 4b, 4c).
- Scope: nothing from `backlog.md` was implemented (no body eval, no human-written queries, no graded relevance, no weighted fusion); no search code or default changed.

## 5. Follow-ups

| ID | Priority | Finding | Decision |
|---|---|---|---|
| F-1 | P2 | The set cannot tell vector from hybrid or the three settings apart: the relevant articles are mostly rewordings of one headline and the full-text leg rarely fires (16 relevant hits) | **addressed 2026-11-04** by M3g `hybrid-eval-set`: entity and low-overlap queries make the full-text leg matter (recall 0.46 on entity queries); hybrid 0.606 vs vector 0.579 recall@5, not a clear win; the sweep still shows no effect of `rrf_k` or `candidates` (ADR-0039) |
| F-2 | P3 | The judge is strict (8.5% yes) and the 3B model's queries sometimes drift; a larger local model (`qwen3:4b-instruct` is pulled) could raise yield and quality | backlog |
| F-3 | P3 | The corpus is a little over the size target (469 KB) | accepted; lower `--distractors` if it matters |
| F-4 | P3 | `embed()` sends a whole list in one request and Ollama failed on 1,557 titles at once; the harness batches by 64, the shared client does not | accepted; the embedder app already batches |
| F-5 | P3 | The fixture freezes one 2-hour window and ages; a rebuild changes the numbers | backlog (CI or scheduled rebuild) |
