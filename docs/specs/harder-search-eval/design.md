# Design — harder-search-eval (M3f)

Reading order: this file → `diagrams/index.html` (components, sequence, data) → ADR-0039 → `design-detail.md` (reference only).

## Idea

Build the benchmark once, freeze it, run it many times. A **builder** reads several real GDELT slots, finds articles that mention the same event (candidates), keeps the members a local model judges to be about the seed's story, asks the model for queries, and writes a **fixture**. The existing **harness** loads that fixture, scores the four methods leave-one-out, sweeps the settings, measures hybrid noise, and applies a stated rule for "a clear win".

## Components (new ids C-90…C-93; nothing in the running platform changes)

| Id | Job | Where |
|---|---|---|
| C-90 builder | slots → articles, mentions → event clusters (candidates) → seeds → judge each member against the seed → queries → fixture. Pure functions (`derive_clusters`, `pick_seeds`, `check_fixture`) plus a thin network + Ollama wrapper; run by hand (`make eval-search-build`), never in CI | `infra/scripts/build_search_eval.py`, `infra/scripts/search_eval_build.py` |
| C-91 fixture | `search_eval_corpus.json` (articles) and `search_eval_queries.json` (queries); real GDELT titles, DR-10 location | `packages/core/tests/fixtures/` |
| C-92 harness | loads a dataset, embeds the corpus per prefix pair, scores `keyword`, `fulltext`, `vector`, `hybrid` leave-one-out, noise measure, sweep, paired bootstrap | `apps/api/tests/eval/` (extends `test_search_eval.py`, new `search_eval_harness.py` support module) |
| C-93 report | the printed tables, then the decision in an ADR or `verify.md` | stdout, docs |

Existing search code (`SemanticService`, repos) is reused unchanged; the old 40-title set stays as the "easy" baseline dataset.

## Key flows

1. **Build (once):** fetch N consecutive slots → parse → dedupe by `story_key` → clusters → seeds → paraphrases → write fixture (diagram 2).
2. **Run (`make eval-search`):** for each dataset and prefix pair: embed corpus, load a throwaway Postgres, run all queries through four methods, print tables (diagram 2).
3. **Sweep (`make eval-search-sweep`):** prefix on/off × `rrf_k` × `candidates`; only the prefix needs re-embedding.
4. **Decide:** the bootstrap rule says keep or change each default; the result goes in the record.

## Contracts

| Item | Shape |
|---|---|
| Corpus row | `{id (= url_hash), title, url, slot}` |
| Query row | `{query, kind ("paraphrase" or "keywords"), cluster (event_id), seed (article id), expected [ids]}`; `expected` = cluster members except the seed |
| Metrics | recall@5, MRR, per method and per kind; seed removed from every result list before scoring |
| Noise | per query: relevant ids in vector top 5 not in hybrid top 5 (and the same against the full-text leg) |
| Win rule | paired bootstrap over queries (1,000 resamples, fixed seed): 95% interval of the MRR difference excludes 0, recall@5 not lower, no kind lower |

## Tricky parts

- **Leave-one-out:** a paraphrase of a title trivially finds that title, so the seed is dropped from results and from `expected`. Without this every method would look good again (the F-5 problem).
- **Duplicates:** syndicated copies of one headline would make fake clusters; articles are collapsed by `story_key` first, like canonicals in the platform.
- **Prefix changes re-embed everything in production:** the embedder re-embeds only on a model-name change, so a winning prefix is a recommendation plus a re-embed plan, not an automatic default change (ADR-0039).
- **Weak queries:** the model may copy the title; AC-3 rejects those at build time and a sample is read by a human before freezing.

## Failure modes

| Failure | Effect |
|---|---|
| GDELT slot missing (404) | the builder skips it and says so; fewer clusters |
| Ollama down at build | builder stops before writing |
| Too few clusters | builder reports the count and exits non-zero rather than freezing a thin set |
| Ollama down at run | the real-model test skips (as today); the fake-embedder tests still run |

## Technology

Python stdlib (`random`, `statistics`), existing `newsdock_core` parsers, `httpx` or `urllib` for GDELT and Ollama (script only), the existing pytest harness. No new dependency.

## AC coverage

| AC | Where |
|---|---|
| AC-1, AC-4 | C-90 `check_fixture`, C-91 |
| AC-2 | C-90 `derive_clusters` |
| AC-13 | C-90 `assemble` (judge step) |
| AC-3 | C-90 query check, C-91 |
| AC-5, AC-8, AC-9 | C-92 run and noise (flow 2) |
| AC-6 | C-92 sweep (flow 3) |
| AC-7 | C-92 real-model run (manual) |
| AC-10 | C-93 decision (flow 4) |
| AC-11 | `make config-python` after a default change |
| AC-12 | existing API suite, no code change |

## Questions to answer before approving this design

- [x] Leave-one-out scoring (seed removed) is the right way to avoid the trivial hit?
- [x] The corpus is all cluster articles plus a sample of distractors, not every title of every slot?
- [x] A winning prefix is only recommended (re-embed plan), never changed automatically?
- [x] The paired-bootstrap rule is an acceptable meaning of "clear win"?
