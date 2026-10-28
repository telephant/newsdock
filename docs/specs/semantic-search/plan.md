# semantic-search — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation

Run 2026-10-28 with grep over `spec.md`, `tests.md`, `design.md` and `tasks/`:

| Check | Result |
|---|---|
| AC → test (AC-1…AC-15 each appear in a TC row) | pass (TC-1…TC-20; AC-8 has TC-8, TC-9; AC-14 has TC-15, TC-16) |
| AC → design (design.md coverage table lists AC-1…AC-15) | pass |
| AC → task (each AC in ≥ 1 task's `Implements`) | pass |
| Orphan tests (TC-1…TC-20 each named in some task's "Tests to turn green") | pass |
| Names consistent (`semantic_search`, `embedding_unavailable`, `invalid_query`, `embedding`, `embedding_model`, `embedding_*` and `semantic_*` settings, `newsdock_embedder`, `newsdock_embedding`, migration `0008_article_embeddings`, `ix_articles_embedding_hnsw`, `ix_articles_title_fts`) | pass |
| No doc treats a Proposed ADR as decided | pass (ADR-0024 and ADR-0025 are Accepted 2026-10-28 on the recommended defaults) |
| Backlog leakage (body extraction, REST route, UI, re-ranking, fuzzy grouping, `halfvec`, side table, `similar_to`) | none in tasks |
| Untagged claims | none new; unverified model facts stay **[memory]** until T-01 |
| Terms missing from the glossary | none |
| Open questions / unchecked checklist items | 2 open design items, neither blocks planning (see R-1, R-2) |

Findings fixed: a garbled sentence in `tests.md` test data.

Open risks carried into implementation (the design review file does not exist, so these come from the design checklist):

- **R-1 (medium):** the ~1 GB vector plus similar-size index at a full window is arithmetic, not measured **[assumption]**. Decision: measure in `/spec-verify` (tests.md Measurements); fall back to `halfvec`, a smaller dimension or fewer days.
- **R-2 (medium):** `nomic-embed-text`, its 768 dimensions and prefixes are **[memory]**; Ollama was not reachable at spec time. Decision: T-01 verifies on the real model. If Ollama is unavailable where the tasks run, T-01 records that, TC-7 and TC-16 stay manual, and every other test uses the fake Ollama.
- **R-3 (low):** the worker accepts that a persistently rejected title is skipped in memory only (restarts retry it once).
- **R-4 (low):** `make test-infra` scenes are still unrun from two earlier verifies; T-03 moves `test_stack.py` to head `0008`, and T-09 runs the scenes if the ports are free.

## Order and reasons

**Spike first (T-01).** The biggest unverified claim is that the real model, its dimension, its prefixes and its speed behave as the design assumes; a different dimension would change the migration (ADR-0025). T-01 also checks that filtered HNSW queries with iterative scan return enough rows and that the `pgvector` Python package works with SQLAlchemy 2. It produces `spike.md`, not code.

Walking skeleton: T-02 (client) and T-03 (schema) give the pieces; T-05 embeds real rows into the real column; T-06/T-07 answer a query through the tool; T-08 measures it. T-04 (pure ranking) has no dependency and can run any time before T-06.

| Task | Title | Implements | Depends on |
|---|---|---|---|
| T-01 | Spike: real model, prefixes, throughput, filtered HNSW | de-risks AC-7, AC-14, AC-15 | none |
| T-02 | Embedding package (`packages/embedding`) | AC-2, AC-4, AC-10, AC-15 | T-01 |
| T-03 | Migration 0008, ORM columns, retention check | AC-1, AC-13 | T-01 |
| T-04 | Pure ranking: reciprocal-rank fusion | AC-8 | none |
| T-05 | Embedder worker app | AC-2, AC-3, AC-4, AC-5, AC-11, AC-15 | T-02, T-03 |
| T-06 | Vector and keyword legs in the API repo and service | AC-6, AC-7, AC-9, AC-11 | T-02, T-03, T-04 |
| T-07 | MCP tool `semantic_search`, API wiring, Ollama route | AC-6, AC-8, AC-9, AC-10, AC-12 | T-06 |
| T-08 | Search eval (recall@5) | AC-14, AC-7 | T-06, T-07 |
| T-09 | Docs, config check, final run | AC-15, all (traceability) | T-05, T-07, T-08 |

## Milestones

- **Skeleton alive (after T-05):** new articles get embeddings on the live stack; AC-1…AC-5.
- **Searchable (after T-07):** `semantic_search` answers over MCP, both modes, with filters and degradation; AC-6, AC-8…AC-13.
- **Measured (after T-08):** recall@5 printed for keyword, vector, hybrid; AC-7, AC-14.
- **Closed (after T-09):** docs agree, `make check` green; AC-15.

## Effort (rough, relative)

T-01 small · T-02 small · T-03 small · T-04 small · T-05 large (new app, compose, healthcheck) · T-06 medium · T-07 medium · T-08 small · T-09 small. No dates.

## Definition of Done (every task)

Tests written first and green · `make check-python` (and `check-web` if touched) green · docs and ADRs updated where the task changes a repeated fact · no secrets · task marked in "Progress" below.

## Progress

(filled by `/spec-implement`)
