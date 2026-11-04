# Tests — harder-search-eval

Derived from the ACs in [spec.md](spec.md) §6. Levels: unit (no I/O), integration (Docker: `side_db` Postgres only, never the dev stack's ports, see `CLAUDE.md`), manual.

## Test data

- **Real data:** the frozen fixture `search_eval_corpus.json` and `search_eval_queries.json` in `packages/core/tests/fixtures/` (DR-10), built once by the builder from real GDELT slots (T-03).
- **Hand-made:** small lists of `CleanArticle` and `CleanMention` built in the unit tests (two copies of one headline, an event with one article, two events sharing an article, a seed that is also a title) so the builder's pure functions are tested without network or Ollama.
- **Fakes:** `FakeOllama` (`newsdock_embedding.testing`) for the harness runs, as in the current eval; the builder's chat call sits behind a function argument so tests pass a stub.
- **Where:** builder tests in `infra/scripts/tests/test_search_eval_build.py`; harness and fixture tests in `apps/api/tests/eval/`; the old 40-title tests stay and keep passing.

## Test cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | unit | Given the frozen fixture, When loaded, Then ids are unique, every cluster has 2 or more articles with different `story_key`, and some corpus articles belong to no cluster |
| TC-2 | AC-2 | unit | Given a hand-made slot with known mentions, When `derive_clusters` runs, Then each cluster is exactly the stored articles mentioning one event, and an article of another event is never in it; an article mentioning two events appears in both |
| TC-3 | AC-2 | unit | Given two copies of one headline and an event mentioned only by them, When `collapse` then `derive_clusters` run, Then there is no cluster for that event |
| TC-4 | AC-3 | unit | Given queries that equal or contain a title, are empty, or are fine, When `check_fixture` runs, Then the first two kinds are rejected and the third passes; the frozen fixture's queries pass |
| TC-5 | AC-4 | unit | Given a query whose `expected` has an id missing from the corpus, outside its cluster, or equal to its seed, When `check_fixture` runs, Then each is rejected; the frozen fixture passes |
| TC-6 | AC-5 | integration | Given the fixture and a fake embedder, When the eval runs, Then it prints recall@5 and MRR for keyword, fulltext, vector and hybrid, overall and by kind |
| TC-7 | AC-5 | unit | Given ranked lists containing a query's seed, When scored leave-one-out, Then the seed is absent from every list before recall and MRR are computed |
| TC-8 | AC-6 | integration | Given the fixture and a fake embedder, When the sweep runs over 2 prefix settings, 4 `rrf_k` and 3 `candidates`, Then 24 rows are printed with recall@5 and MRR for vector and hybrid |
| TC-9 | AC-8 | unit | Given hand-made vector and hybrid lists, When `noise` runs, Then it counts the relevant vector top-5 ids missing from the hybrid top 5, and the same against the full-text list |
| TC-10 | AC-8 | integration | Given the fixture and a fake embedder, When the eval runs, Then the noise line is printed |
| TC-11 | AC-9 | integration | Given the same fixture and settings, When the eval runs twice, Then the printed numbers are identical |
| TC-12 | AC-6 | unit | Given paired scores, When `paired_bootstrap` runs, Then it is deterministic for a fixed seed, its interval excludes 0 for clearly different scores and includes 0 for identical ones |
| TC-13 | AC-7 | manual | Given the real model and the fixture, When `make eval-search` runs, Then keyword, vector and hybrid do not all score the same recall@5 and MRR |
| TC-14 | AC-10 | manual | Given the real-model sweep, When the owner reads the result, Then ADR-0039's Result section (or `verify.md`) names the chosen prefix, `semantic_rrf_k` and `semantic_candidates` with their numbers and says kept or changed for each |
| TC-15 | AC-11 | integration | Given any default changed or none, When `make config-python` runs, Then it passes |
| TC-17 | AC-13 | unit | Given candidates and a judge that rejects one member, When the fixture is assembled, Then the rejected member is not in `members` or `expected` but is in the corpus; and a cluster with no verified member makes no queries |
| TC-16 | AC-12 | integration | Given the existing API suite, When it runs, Then it passes with no change to tools, routes or payloads |

## Manual checklist (TC-13, TC-14)

1. Ollama running with `nomic-embed-text`; run `make eval-search`; read the overall and by-kind tables.
2. Confirm the methods differ (TC-13). If vector and hybrid still tie at 1.000, the set is too easy: stop and rebuild harder, do not close the milestone.
3. Read the sweep table and the bootstrap verdicts; write kept or changed per setting with the numbers into ADR-0039's Result section (TC-14).
4. Read 20 queries from the fixture by eye: none a copy of its seed, most plausible as searches.

## Coverage

AC-1 TC-1 · AC-2 TC-2, TC-3 · AC-3 TC-4 · AC-4 TC-5 · AC-5 TC-6, TC-7 · AC-6 TC-8, TC-12 · AC-7 TC-13 · AC-8 TC-9, TC-10 · AC-9 TC-11 · AC-10 TC-14 · AC-11 TC-15 · AC-12 TC-16 · AC-13 TC-17.

## Measurements (provisional, not pass/fail)

| Target (spec §7) | How |
|---|---|
| Number of clusters, queries per kind, corpus size | printed by the builder (T-01 and T-03) |
| Fixture size on disk | `ls -l` of the two files, target a few hundred KB |
| Eval run time (fake and real embedder) | wall clock of `make eval-search` and the sweep |
| Builder determinism | two builds from the same cached slots with the same stub give identical files |
| Query quality | the 20-query read of the checklist |
