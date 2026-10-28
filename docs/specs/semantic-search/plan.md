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

- **R-1 (medium):** about 2.8 GB total (HNSW about 1.4 GB) at a full window, extrapolated from 50,000 rows in the spike. Decision: confirm the real size in `/spec-verify` (tests.md Measurements); fall back to `halfvec`, a smaller dimension or fewer days.
- **R-2 (low, was medium):** the model, its 768 dimensions, the endpoint and its speed were verified in T-01 (spike.md). Still open: whether the task prefixes help; T-08 compares both settings on the eval corpus.
- **R-5 (low):** because `embedding` is indexed, each embedding UPDATE also writes the other seven indexes of `articles` and leaves one dead tuple; the HNSW insert (about 7.5 ms a row) dominates, so the worker runs at about 130 rows/s and a full backfill takes about 45 minutes **[estimate]**. Decision: ADR-0025 stands (a side table would break filtered search); measure the real backfill at verify.
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

- T-01 ✅ 2026-10-28 — spike, findings in [spike.md](spike.md); no production code. Verified: `nomic-embed-text` returns 768-dim finite vectors via `/api/embed` at about 205 titles/s; a missing model is a clean 404 JSON error; pgvector 0.8.7 HNSW needs `iterative_scan` for filtered queries (1 of 20 rows without, 20 of 20 with `relaxed_order` or `strict_order`); `pgvector` 0.5.1 works with SQLAlchemy 2.1.3 and psycopg 3.3 on Python 3.12; the agent reaches Ollama through `host.docker.internal` with no `extra_hosts`. Found: index build on 50k rows took 176 s (not paid, the migration builds on an empty column), HNSW is 195 MB per 50k rows, embedding UPDATEs are index-bound at about 130 rows/s (R-5); prefixes inconclusive (T-08 compares). Side effects on this machine: `nomic-embed-text` was pulled and a local `ollama serve` was started; the throwaway pgvector container was removed.
- T-02 ✅ 2026-10-28 — `packages/embedding` (`newsdock_embedding`): `embed(texts, model=, url=, timeout=, client=None)` (one `POST /api/embed`, nothing sent for an empty list), `document_text` / `query_text`, `validate`, errors `OllamaUnavailable` (connection, timeout, non-200 with the body clipped to 200 characters, body without embeddings) and `BadEmbedding` (wrong count, length or non-finite), and `newsdock_embedding.testing.FakeOllama` (deterministic vectors, nine failure modes). TC-18 green (18 tests in `tests/unit/test_client.py`). Root `pyproject.toml`: mypy path, import-linter root plus contracts (the package imports no app, core, config or db; core and every `domain/` may not import it). `make check-python`: 517 passed (499 + 18), lint, mypy strict, import-linter, layout and config checks green. Two corrections to the task, written into T-02 and T-05: the `common:` config rows move to T-05 (a `common` key no service declares fails `make config-python`), and the fake lives in the package, not `tests/fakes.py`. CI already covers it (`packages/**`). AC-2, AC-4, AC-10 and AC-15 stay `in-progress`: they close in T-05, T-06 and T-07.
- T-03 ✅ 2026-10-28 — migration `0008_article_embeddings` (forward-only, DR-11): `articles.embedding vector(768)` and `embedding_model text`, both nullable; `ix_articles_embedding_hnsw` (cosine, m 16, ef_construction 64) and `ix_articles_title_fts` (GIN on `to_tsvector('english', title)`); NOLOGIN role `embedder_rw` with `SELECT` on `articles` and `UPDATE (embedding, embedding_model)`. `Article` gained the two columns and both indexes; `newsdock-db` depends on `pgvector>=0.5` (lockfile updated, the migrate image builds and imports it). `test_stack.py` now expects head `0008`. TC-1 green (3 tests in `apps/api/tests/integration/test_embedding_migration.py`: columns/indexes/rows unchanged, role grants, autogenerate no-op) and TC-14 green (`apps/sink/tests/integration/test_embedding_retention.py`, with a new `conftest.py` `side_db` on port 55434 so it runs beside the dev stack). `make check-python`: 517 passed, lint, mypy strict, import-linter, layout and config green. Docker: the 8 `side_db` modules (51 tests, including the earlier ownership, signup-limit, subscription and scope suites) pass. AC-1 and AC-13 `passing`. Corrections: no downgrade (DR-11), the role is new (the design only said the worker updates the columns), and tests.md / design-detail were fixed to match. Not run: the modules that start their own Postgres on port 5433 (the dev stack holds it; the known open item R-4), so the older `packages/db` schema test was not re-run; its autogenerate no-op is covered by this task's third test. One non-reproducible failure appeared in the first of three full runs of the API and sink Docker suites (the next two had none); I could not identify it.
- T-04 ✅ 2026-10-28 — `apps/api/src/newsdock_api/domain/ranking.py`: `fuse(legs, k=)` over a mapping of leg name to ranked hits (`Ranked(id, published_at)`), returning `Fused(id, score, matched_by)` best first; score is the sum of `1/(k+rank)` per leg, a repeated id in one leg counts once at its first rank, ties break by newest `published_at` then id, `k <= 0` raises `ValueError`. TC-8 green (11 tests in `apps/api/tests/unit/test_ranking.py`); one test I first wrote could not fail whatever `k` was, so it was replaced by an exact check (A first in one leg vs B third in both: B wins at k=60, tie at k=1). `make check-python`: 528 passed, lint, mypy strict, import-linter (the module is pure) green. AC-8 stays `in-progress` until TC-9 in T-07.
