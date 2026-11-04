# Verify — hybrid-eval-set (M3g)

Run 2026-11-04. **Verdict: pass with follow-ups, all 12 ACs.** The harder set makes the full-text leg matter (recall 0.46 on entity queries) and hybrid edges ahead of vector, but not by a clear margin, so every default is kept (F-1).

## 1. Runs

| Run | Result |
|---|---|
| `make check-python` (ruff, mypy strict, import-linter, layout, config, unit tests) | 1,219 passed, 530 Docker-marked deselected |
| Whole API suite incl. Docker modules and the real-model eval tests | 857 passed in 13 min (852 before this milestone) |
| `make docs-check`, `make config-python` | clean |
| `make eval-search` (real model, three datasets, prefixes on and off) | passed; `events-hard` numbers in §3 |
| `make eval-search-sweep` (real model, `events` and `events-hard`, 24 rows each) | passed (194 s) |
| `make eval-search-build-hard` repeated | byte-identical file (`shasum` equal) |

## 2. Acceptance criteria

| AC | TC | Result | Evidence |
|---|---|---|---|
| AC-1 | TC-1 | pass | `test_names_are_cut_cleanly_from_a_title` (8 cases: outlet suffix, HTML entity, possessive, sentence-initial word, acronym, no name, duplicates and limit), `test_the_name_limit_can_be_lowered` |
| AC-2 | TC-2 | pass | `test_the_frozen_hard_queries_pass_the_checker`, `test_both_kinds_are_present_and_entity_queries_are_names`, `test_a_name_phrase_may_sit_inside_a_title_but_a_copy_may_not` (rule amended at T-03, see §4) |
| AC-3 | TC-3 | pass | `test_members_are_graded_by_their_word_overlap_with_the_seed`, `test_hard_queries_have_entity_and_low_overlap_rows` (a cluster of rewordings makes no low-overlap query) |
| AC-4 | TC-4 | pass | `test_check_hard_fixture_rejects_broken_rows` (5 cases), the repeated-text and two-names tests, the frozen file passes |
| AC-5 | TC-5 | pass | `test_the_builder_is_offline_and_repeatable` (socket patched to raise; two outputs equal each other and the committed file) |
| AC-6 | TC-6 | pass | `test_ignored_ids_and_the_seed_are_removed_before_the_first_k`, `test_an_ignored_article_neither_hits_nor_pushes_a_graded_one_down` |
| AC-7 | TC-7 | pass | `test_the_events_hard_eval_prints_entity_and_lowoverlap_kinds` |
| AC-8 | TC-9 | manual-ok | real model, `events-hard`: full-text recall on `entity` queries 0.46 (§3) |
| AC-9 | TC-8 | pass | `test_the_sweep_has_one_row_per_combination[events-hard]` (24 rows, clear-win list) |
| AC-10 | TC-10 | manual-ok | ADR-0039 "Result of the M3g set": prefix kept, `semantic_rrf_k` kept at 60, `semantic_candidates` kept at 50, with numbers and the vector-versus-hybrid answer |
| AC-11 | TC-11 | pass | `make config-python` clean (no default changed) |
| AC-12 | TC-12 | manual-ok | the diff of `corpus.json`, `queries.json`, `search_eval_corpus.json`, `search_eval_queries.json` and every `src` folder since the design commit is empty; only `search_eval_hard_queries.json` was added under `packages/` |

## 3. Measurements (real data, real model)

| Target (spec §7) | Reading |
|---|---|
| Method scores, `events-hard` (74 queries), prefixes on | keyword 0.041 / 0.041, full-text 0.261 / 0.222, vector 0.579 / 0.449, hybrid 0.606 / 0.454 (recall@5 / MRR) |
| By kind (recall@5) | entity: keyword 0.07, full-text **0.46**, vector 0.64, hybrid 0.69; low-overlap: keyword 0.00, full-text 0.00, vector 0.50, hybrid 0.50 |
| Hybrid noise | of 45 relevant vector top-5 hits hybrid dropped 0; of 21 relevant full-text hits it dropped 1 |
| Hybrid versus vector (paired bootstrap, T-05) | 7 of 74 queries differ; MRR interval [-0.033, +0.048]; recall [0.000, +0.068]; entity recall [0.000, +0.119] |
| Sweep | 24 rows; `semantic_rrf_k` and `semantic_candidates` change nothing with prefixes on; clear wins over the defaults: 0 |
| Query counts | 42 entity, 32 low-overlap (spike estimate 48 and 32; the common-word filter removed 3 names that were verbs) |
| Builder run time and file size | about 0.1 s offline; 31 KB |
| Real-model eval time | `make eval-search` about 77 s for the `events-hard` portion; sweep 194 s for both datasets |
| Entity-name quality (15 read) | about 12 clean story names; weak ones remain (`Presses Mathanga Protests`, `US Americans Iran`, `Senate Trump`) |

## 4. Drift and scope

- Recorded during the work: AC-2 amended at T-03 (a name phrase may sit inside a title; a query equal to a title or containing a whole one is still a copy; the strict rule had rejected 15 of 48 good name queries), the common-word filter and `grade_members` signature in `design-detail.md` §1 and §7, the ADR-0039 "M3g extension" and Result sections.
- Names are identical across code and docs (`extract_names`, `grade_members`, `build_hard_queries`, `check_hard_fixture`, `without`, `events-hard`, `search_eval_hard_queries.json`, `make eval-search-build-hard`).
- Scope: nothing from `backlog.md` was implemented (no weighted fusion, no OR-style keyword leg, no NER, no new corpus); no search code or default changed. The root `pyproject.toml` pytest `pythonpath` and mypy `mypy_path` entries added in M3f are reused.

## 5. Follow-ups

| ID | Priority | Finding | Decision |
|---|---|---|---|
| F-1 | P2 | Hybrid is slightly ahead of vector on name queries (recall +0.05 from 2 queries) but not by a clear margin; an alternative fusion or an OR-style keyword leg (the leg ANDs every word) would need a larger set and its own spec | backlog (`hybrid-eval-set`): more queries where the keyword leg matters, then argue any fusion change |
| F-2 | P3 | Entity names come from a capitalised-word heuristic; about 3 of 15 read are weak | backlog: a name recogniser |
| F-3 | P3 | The low-overlap kind has 32 queries and all rewordings were ignored, so intervals are wide | backlog: a bigger corpus or more slots |
| F-4 | P3 | The whole API suite now takes 13 minutes because the real-model eval tests run in it when Ollama is up | accepted; they skip without Ollama |
