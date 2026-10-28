# semantic-search — T-01 spike findings

Run 2026-10-28 on the owner's machine (macOS, Docker 29.8.1, Ollama local server started for the spike). Scripts were throwaway (not committed). Every number below was measured in this session unless marked otherwise.

## 1. Ollama and `nomic-embed-text`

| Question | Finding |
|---|---|
| Model present? | No. `ollama pull nomic-embed-text` (about 270 MB) was run for this spike; `ollama rm nomic-embed-text` removes it. Models already installed: `qwen3:4b-instruct`, `llama3.2:3b`, `llama3.2:1b` **[verified]** |
| Dimension | 768, all values finite **[verified]** |
| Endpoint | `POST /api/embed` with `{"model", "input": [...]}` returns `embeddings` **[verified]** |
| Throughput | batch of 32: 204.8 titles/s; batch of 256: 208.4 titles/s (synthetic 12-word titles, this machine) **[verified]**. A 350,000-title window would take about 28 minutes of embedding alone |
| Model not pulled | HTTP 404, body `{"error":"model \"…\" not found, try pulling it first"}` **[verified]** → `OllamaUnavailable` as designed (TC-18) |
| Prefixes | Inconclusive. On 5 hand-made paraphrase pairs both variants ranked the right document first (5/5); the mean margin to the best distractor was 0.22 without prefixes and 0.15 with `search_query:` / `search_document:` **[verified]**. Five pairs are too few to choose. Decision: keep the prefixes as config and compare both on the eval corpus in T-08 |

## 2. pgvector 0.8.7 on `pgvector/pgvector:0.8.7-pg16-trixie` (50,000 random 768-d rows)

| Question | Finding |
|---|---|
| HNSW cosine build, m 16, ef_construction 64 | 176 s on 50,000 rows with the default `maintenance_work_mem` (a NOTICE said the graph no longer fit after 17,699 tuples) **[verified]**. The migration creates the index on an empty column, so it is not paid there |
| Incremental insert into the existing index | 500 rows in 3.8 s, about 7.5 ms a row **[verified]**; this bounds the worker at about 130 rows/s, below the model's 205 titles/s. Backfilling 350,000 rows is about 45 minutes **[estimate]** |
| Size at 50,000 rows | HNSW index 195 MB; whole relation (heap, TOAST, HNSW, GIN) 400 MB **[verified]** → about 1.4 GB of HNSW and about 2.8 GB in total at 350,000 rows **[extrapolated]** |
| Filtered query, 1% filter, `LIMIT 20`, planner forced onto the HNSW index | `iterative_scan = off`, `ef_search = 40`: **1 row** returned; `relaxed_order`, `ef_search = 100`: **20 rows** (70 ms); `strict_order`: **20 rows** (47 ms) **[verified]** → the iterative scan is required for filtered search (design §4) |
| Unforced planner on the same 1% filter | chose a sequential scan with sort (exact results) **[verified]**; both paths return enough rows |
| Unfiltered top-20 through the index | about 10 ms **[verified]** |
| `set_config('hnsw.iterative_scan', 'relaxed_order', true)` inside a transaction | works, returns 20 rows **[verified]** (parameterized `SET LOCAL`, design-detail §4) |
| FTS GIN index on `to_tsvector('english', title)` | builds in 88 ms on 50,000 rows **[verified]** |

## 3. `pgvector` Python package

`pgvector` 0.5.1 with SQLAlchemy 2.1.3, `psycopg[binary]` 3.3 and Python 3.12.14: `Vector(768)` maps, reads return a list of 768 floats, `cosine_distance` ordering works, and a list can be written **[verified]**. It is not yet a dependency of `newsdock_db` (T-03 adds `pgvector>=0.5`).

## 4. How the agent reaches Ollama

The `agent` compose service sets `OLLAMA_URL: http://host.docker.internal:11434` and has no `extra_hosts`; Docker Desktop on macOS resolves the name **[verified: `infra/compose.yaml`]**. The embedder and API copy that environment line (T-05, T-07). On Linux an `extra_hosts: host.docker.internal:host-gateway` line would be needed **[memory]**; the project targets macOS Docker.

## 5. What the spike changes

- **Verified, tags updated:** 768 dimensions, endpoint, error shape, throughput, pgvector version and package compatibility.
- **R-1 refined (capacity):** about 2.8 GB total relation size at a full window, not "about 1 GB plus a similar index" as roughly 1.1 GB raw vectors suggested; the HNSW index alone is about 1.4 GB. `halfvec` stays the first fallback.
- **New R-5 (write cost):** because `embedding` is indexed, each embedding UPDATE is not a heap-only update, so it also writes entries into the other indexes of `articles` (seven today: primary key, `seq`, `published_at`, `ingested_at`, `themes` GIN, `domain`, `story_key`+`published_at`, plus the two new ones). The HNSW insert dominates (7.5 ms a row); the rest is expected to be small but was not measured on the real schema. One dead tuple per article is left for autovacuum. A side table would avoid this but breaks filtered search (iterative scan cannot see join filters), so ADR-0025's decision stands. Measure the real backfill in `/spec-verify`.
- **Prefixes:** open, resolved by the eval in T-08.
- No contradiction with the spec's acceptance criteria; no ADR changes decision.
