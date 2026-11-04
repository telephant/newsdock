# Tests — hybrid-eval-set

Derived from the ACs in [spec.md](spec.md) §6. Levels: unit (no I/O), integration (Docker: `side_db` Postgres only, never the dev stack's ports, see `CLAUDE.md`), manual.

## Test data

- **Real data:** the frozen corpus and queries of M3f (`search_eval_corpus.json`, `search_eval_queries.json`) and the generated `search_eval_hard_queries.json`, all in `packages/core/tests/fixtures/` (DR-10).
- **Hand-made:** seed titles with proper names, outlet suffixes (` | Outlet`), HTML entities, sentence-initial words, acronyms and no names at all; small clusters with high- and low-overlap members; ranked lists holding a seed and ignored ids.
- **Fakes:** `FakeOllama` for the harness runs, as before. The builder needs none (offline).
- **Where:** builder tests in `infra/scripts/tests/test_search_eval_build.py` and `test_search_eval_hard_fixture.py`; harness tests in `apps/api/tests/eval/` (`test_harness_units.py`, `test_search_eval.py`).

## Test cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | unit | Given seed titles with names, an outlet suffix, an HTML entity, a sentence-initial word, an acronym, and one with no name, When `extract_names` runs, Then at most 3 names come back in title order without punctuation, sentence-initial and stoplist words are skipped, acronyms are kept, and the no-name title gives `[]` |
| TC-2 | AC-2 | unit | Given the frozen hard-queries file and corpus, When each entity query is checked, Then none is empty, equals a corpus title or contains a whole one (a name phrase may sit inside a title) and each has 2 or more name words |
| TC-3 | AC-3 | unit | Given a cluster with a high-overlap and a low-overlap member, When `grade_members` runs, Then the low-overlap one is graded and the other ignored; a cluster whose members are all high-overlap makes no low-overlap query |
| TC-4 | AC-4 | unit | Given hard-queries rows with an unknown id, overlapping `expected` and `ignore`, a member outside the cluster, or a repeated text within a kind, When `check_hard_fixture` runs, Then each is rejected; the frozen file passes |
| TC-5 | AC-5 | unit | Given the frozen files and a socket that raises on use, When the builder runs twice, Then it makes no network call and both outputs are byte-identical |
| TC-6 | AC-6 | unit | Given ranked lists with the seed and ignored ids, When scored, Then both are removed before recall and MRR and the first k remain |
| TC-7 | AC-7 | integration | Given `events-hard` and a fake embedder, When the eval runs, Then recall@5 and MRR print for the four methods overall and for `entity` and `lowoverlap`, with the noise line |
| TC-8 | AC-9 | integration | Given `events-hard` and a fake embedder, When the sweep runs, Then 24 rows print with the clear-win list |
| TC-9 | AC-8 | manual | Given the real model and `events-hard`, When `make eval-search` runs, Then the full-text recall on the `entity` kind is above zero |
| TC-10 | AC-10 | manual | Given the real-model sweep on `events-hard`, When the result is read, Then ADR-0039's Result says kept or changed for prefix, `semantic_rrf_k` and `semantic_candidates` with numbers, and whether vector and hybrid differ |
| TC-11 | AC-11 | integration | Given any default changed or none, When `make config-python` runs, Then it passes |
| TC-12 | AC-12 | manual | Given the `easy` and `events` data, When the milestone is done, Then `git diff` shows the four earlier fixture files and `apps/*/src` unchanged |

## Manual checklist (TC-9, TC-10, TC-12)

1. Ollama running with `nomic-embed-text`; run `make eval-search`; read the `events-hard` tables by kind (TC-9: full-text recall on `entity` above zero; if it is 0, the names are wrong or the AND query is too strict: stop and fix the extractor).
2. Run `make eval-search-sweep` on `events-hard`; read the clear-win list; write kept or changed per setting and whether vector and hybrid differ into ADR-0039's Result (TC-10).
3. `git diff --stat -- packages/core/tests/fixtures/search_eval_corpus.json packages/core/tests/fixtures/search_eval_queries.json apps/api/tests/eval/corpus.json apps/api/tests/eval/queries.json apps/*/src` is empty (TC-12).
4. Read 15 entity queries by eye: names of the story, no verbs, no stray words.

## Coverage

AC-1 TC-1 · AC-2 TC-2 · AC-3 TC-3 · AC-4 TC-4 · AC-5 TC-5 · AC-6 TC-6 · AC-7 TC-7 · AC-8 TC-9 · AC-9 TC-8 · AC-10 TC-10 · AC-11 TC-11 · AC-12 TC-12.

## Measurements (provisional, not pass/fail)

| Target (spec §7) | How |
|---|---|
| Builder run time | wall clock of `make eval-search-build-hard` |
| Hard-queries file size | `ls -l` |
| Number of entity and low-overlap queries | printed by the builder (T-01 estimates 51 clusters with 2+ names and 32 with a low-overlap member) |
| Real-model eval time on `events-hard` | wall clock of `make eval-search` and the sweep |
| Entity-name quality | the 15-query read of the checklist |
