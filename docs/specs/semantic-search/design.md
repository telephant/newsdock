# semantic-search — Design (Milestone 3, part 1)

Status: **approved on defaults** · 2026-10-28 · Spec: [spec.md](spec.md) · Detail (not required reading): [design-detail.md](design-detail.md)

**Reading order:** this file → `diagrams/index.html` (each diagram has a "Check" box) → ADR-0024, ADR-0025 in `../../adr/` → the checklist at the bottom.

## 1. Components (ids continue from C-34; unchanged components not listed)

| Id | Component | Change | Notes |
|---|---|---|---|
| C-35 | Embedder worker (`apps/embedder`) | **new app** | Polls Postgres for canonical articles with no embedding for the configured model, embeds titles in batches through Ollama, writes vector + model name. No Kafka, no API calls (ADR-0024) |
| C-36 | Embedding package (`packages/embedding`, `newsdock_embedding`) | **new package** | The one Ollama `/api/embed` client, the document/query text prefixes, and vector validation (length, finite). Used by C-35 and C-37 so both embed identically |
| C-37 | Semantic query (`domain/ranking.py`, `adapters/semantic_repo.py` in the API) | **new** | Vector leg (HNSW, cosine), keyword leg (Postgres full-text), pure RRF fusion, shared filters |
| C-38 | MCP tool `semantic_search` (in `adapters/http.py`) | **new tool** | Inherits the existing auth and rate-limit path of `/mcp`; maps errors to `embedding_unavailable` / degraded results |
| C-39 | Migration `0008_article_embeddings` | **new** | `articles.embedding vector(768)`, `articles.embedding_model`, HNSW cosine index, GIN index on `to_tsvector('english', title)` |
| C-40 | Search eval (`apps/api/tests/eval/`, `make eval-search`) | **new** | Fixture corpus + labelled queries; prints recall@5 for keyword, vector, hybrid |
| C-4 | Sink retention | unchanged | The embedding lives on the article row, so the existing 7-day `DELETE` removes it (AC-13) |
| C-5 | PostgreSQL | **changed** | New columns and two indexes (C-39) |
| C-6 | API repo/service | **changed** | `_apply_filters` is reused by the vector and keyword legs, so filters have one implementation |

Ingester, processor, sink, demo agent and web: unchanged.

## 2. Key flows

- **F-16 Embed:** C-35 selects up to `batch_size` canonical rows where `embedding IS NULL OR embedding_model <> :model`, newest first → C-36 embeds `"<doc prefix><title>"` → one UPDATE per row, guarded so a concurrent change is not overwritten. (Sequence 1)
- **F-17 Backfill:** the same loop; rows from before the migration have `embedding IS NULL` and are picked up newest first until nothing is left. (Sequence 1)
- **F-18 Query:** agent → `/mcp` (key, rate limit) → C-38 → C-36 embeds `"<query prefix><query>"` → C-37 runs the vector leg and the keyword leg with the same filters → RRF → summaries with `score`. (Sequence 2)
- **F-19 Degraded:** Ollama unreachable at query time → `vector` mode returns tool error `embedding_unavailable`; `hybrid` returns the keyword leg with `degraded: true`. (Sequence 2)
- **F-20 Model change:** the configured model differs from a row's `embedding_model` → vector leg ignores the row, C-35 re-embeds it. (State diagram 4)

## 3. Contracts

**`articles` (new columns):** `embedding vector(768)` NULL, `embedding_model text` NULL. Indexes: `ix_articles_embedding_hnsw` (`hnsw (embedding vector_cosine_ops)`, m 16, ef_construction 64) and `ix_articles_title_fts` (`gin (to_tsvector('english', title))`).

**MCP `semantic_search`**

| Argument | Type | Default | Notes |
|---|---|---|---|
| `query` | string | required | 1…`semantic_query_max_length` chars |
| `mode` | `vector` \| `hybrid` | `hybrid` | |
| `limit` | int | service default | capped like `search_articles` |
| `time_from`, `time_to`, `theme`, `domain` | as `search_articles` | none | `theme` accepts a trailing `*` |

Result: `{"articles": [ArticleSummary + "score" + "matched_by"], "mode": "...", "degraded": false}`. `score` = cosine similarity in `vector` mode, RRF score in `hybrid`; `matched_by` ⊆ {`vector`,`keyword`}.

Errors: `embedding_unavailable` (vector mode, Ollama down or wrong dimension), `invalid_query` (empty or too long), `unauthorized` / rate limit as for every tool.

**Config (ADR-0013).** `common:` (read only by apps that declare the field): `embedding_model` (`nomic-embed-text`), `embedding_dimension` (768), `embedding_document_prefix`, `embedding_query_prefix`, `embedding_ollama_url` (env `OLLAMA_URL`). `embedder:` `batch_size` (32), `poll_interval_seconds` (10), `idle_poll_seconds` (30), `ollama_timeout_seconds`, `backoff_seconds`. `api:` `semantic_candidates` (50), `semantic_rrf_k` (60), `semantic_query_max_length` (500), `semantic_ef_search` (100), `semantic_ollama_timeout_seconds`. All numbers are starting points to be measured, not requirements.

## 4. Tricky parts

- **Embedding never blocks ingest (D-3):** a separate process reading committed rows; the sink knows nothing about it.
- **Filters with HNSW:** an ANN index applies filters after the scan, so a selective filter can return too few rows. Each vector query sets `hnsw.iterative_scan = relaxed_order` and re-sorts by exact distance **[verified: pgvector 0.8 README]**.
- **Dimension is schema:** `vector(768)` is fixed in the migration. Same-dimension model swaps need no migration; a different dimension needs a new migration (ADR-0025). A returned vector with the wrong length is rejected, never stored.
- **Same text recipe on both sides:** documents and queries go through C-36 with their own prefixes. nomic models expect task prefixes **[memory]**; the prefixes are config, and the first plan task checks them on the real model.
- **Ollama down is normal:** the worker keeps its heartbeat (alive, not stuck) and backs off; the container is not restarted for a dependency outage.
- **Idempotency:** the UPDATE only fires for rows still needing it, so a second pass sends no request (AC-3).
- **Ranking is pure:** RRF takes two ranked id lists and returns one; it is unit-tested without a database.

## 5. Failure modes (top)

| Failure | Result |
|---|---|
| Ollama down (worker) | rows stay unembedded, logged, retried with backoff; ingest unaffected |
| Ollama down (query) | `vector`: `embedding_unavailable`; `hybrid`: keyword leg, `degraded: true` |
| Model not pulled | same as down; the log line names the model |
| Wrong vector length | row skipped and logged; never written |
| Selective filter, few rows | iterative scan; still returns fewer than `limit` only if fewer exist |
| Model changed | old rows excluded from vector results until re-embedded |
| Embedder restart | stateless; resumes from the query |

## 6. Technology

Postgres + pgvector 0.8 HNSW **[verified: image tag `pgvector/pgvector:0.8.7-pg16-trixie`; README]**; Ollama `POST /api/embed` with a list `input` **[verified: Ollama API docs]**; model `nomic-embed-text` (768 dimensions **[verified: spike.md]**, 2K context **[verified: ollama.com]**); psycopg/SQLAlchemy as today; `httpx` for Ollama (already used by the agent **[assumption]**). `pgvector` Python package for the SQLAlchemy `Vector` type **[assumption: a new dependency of `newsdock_db`]**.

## 7. AC coverage

| AC | Component / flow |
|---|---|
| AC-1 | C-39 |
| AC-2, AC-3 | C-35, C-36 / F-16 |
| AC-4 | C-35 (D-3), C-4 untouched / F-16 |
| AC-5 | C-35 / F-17 |
| AC-6, AC-9 | C-37, C-38 / F-18 |
| AC-7 | C-36, C-37 / F-18 |
| AC-8 | C-37 (RRF) / F-18 |
| AC-10 | C-38 / F-19 |
| AC-11 | C-35, C-37 / F-20 |
| AC-12 | C-38 (existing `/mcp` auth and limiter) |
| AC-13 | C-4 + C-39 (same row) |
| AC-14 | C-40 |
| AC-15 | config of C-35, C-37, C-36 |

## Questions to answer before approving this design

- [x] A new `embedder` app plus a `packages/embedding` package, not extra work inside the sink (ADR-0024; accepted on defaults 2026-10-28).
- [x] Embeddings as columns on `articles` (not a side table), HNSW cosine, fixed 768 dimensions (ADR-0025; accepted on defaults).
- [x] The keyword leg of hybrid is Postgres full-text (`english`) on the title with a GIN index, not `ILIKE` (spec D-8, amends AC-1; accepted on defaults).
- [x] The worker stays healthy while Ollama is down (a dependency outage is not a reason to restart it).
- [ ] About 2.8 GB in total (HNSW about 1.4 GB) at a full 350k-row window is acceptable on the dev machine **[extrapolated from 50k rows in spike.md]**; `halfvec` is the fallback (backlog).
- [x] `nomic-embed-text` runs here: 768 dimensions, about 205 titles/s, clean 404 when not pulled (T-01 spike, 2026-10-28). Whether its task prefixes help is still open and is compared on the eval corpus in T-08.
