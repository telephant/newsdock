# semantic-search — Verify

Run 2026-10-28/29. Spec: [spec.md](spec.md) · Tests: [tests.md](tests.md) · Plan: [plan.md](plan.md)

**Verdict: pass with follow-ups.** All 15 ACs pass in this run. Measuring on real data found one scaling flaw in the embedder (F-1); it was fixed during verify (T-10, migration 0009, spec D-9) and re-measured.

## 1. What was run

| Run | Result |
|---|---|
| `make check` (Python: lint, mypy strict, import-linter, layout, config; web; docs), after the fix | exit 0; Python 599 passed, web 166 passed |
| Docker suites on throwaway Postgres: `apps/api/tests`, `apps/sink/tests`, `apps/embedder/tests`, `packages/db/tests` with `-m docker`, including the real-Ollama tests, after the fix | 214 passed, 0 failed |
| Real-data measurement: a read-only copy of 99,401 GDELT articles from the dev database, the real `nomic-embed-text`, the real `python -m newsdock_embedder` process | finished; numbers in §3 |
| Dev database before and after each Docker run | unchanged (2 users, 14 agents, 14 keys, 12 subscriptions, 1 cursor, still migration `0008`); no stray containers |

**Not run:** the Kafka modules (`ingester`, `processor` integration) and the whole-stack scripts (`test_stack`, `test_images`, `test_reingest`, `test_story_agent`, `test_agent_isolation`). They start their own stack on the dev stack's fixed ports, so the `dev_stack_guard` plugin refuses them while the dev stack runs. So the nine-service health test, the head check (`0009`) in `test_stack.py` and the image-contract tests have not been executed. The compose file parses and lists `embedder`; the `embedder`, `api` and `migrate` images were built and import (before T-10; T-10 changes no dependency or Dockerfile). Run these with the dev stack stopped.

## 2. Acceptance criteria

| AC | Tests (this run) | Result | Evidence |
|---|---|---|---|
| AC-1 schema | TC-1 `test_embedding_migration.py` (4) | pass | columns, HNSW, GIN and (0009) partial indexes, `embedder_rw` grants, rows unchanged, autogenerate no-op. On real rows: GIN full-text build 0.64 s, HNSW on the all-NULL column 0.02 s |
| AC-2 new article embedded | TC-2 `test_embedder_db.py`, TC-18 `test_client.py` | pass | real process and model: all 99,401 rows have 768-dim vectors and `embedding_model = nomic-embed-text` |
| AC-3 idempotent | TC-3 `test_loop.py` | pass | an idle pass, a second pass and a restart with the same model send no request |
| AC-4 Ollama down | TC-4 `test_embedder_db.py`, TC-18, TC-19 `test_loop.py` | pass | rows stay empty, heartbeat kept, backoff doubles to 60 s, recovery fills them |
| AC-5 backfill | TC-5, TC-21 `test_embedder_db.py` | pass | 120 rows newest first in 4 passes; the batch query uses the partial index with 29,900 of 30,000 rows already embedded; on real data all 99,401 rows backfilled at a steady ~94 rows/s |
| AC-6 vector order | TC-6 `test_semantic_repo.py`, `test_semantic_mcp_api.py`, TC-20 | pass | ascending distance, score = cosine similarity in [-1, 1], `invalid_query` before any embedding call |
| AC-7 paraphrase | TC-7 `test_semantic_ollama.py` (2) | pass | real model through the live MCP tool: "interest rate hike" finds "Central bank lifts borrowing costs" first; the substring search does not. On real data: "Bank of Canada hikes interest rate to 2.5%" first |
| AC-8 hybrid fuses | TC-8 `test_ranking.py` (11), TC-9 `test_semantic_mcp_api.py` | pass | an article in both legs ranks first; `matched_by` correct |
| AC-9 filters | TC-10 `test_semantic_repo.py`, `test_semantic_mcp_api.py` | pass | domain, exact and `ECON_*` theme, time range, both modes; a 1% filter still returns every match |
| AC-10 Ollama down at query | TC-11 `test_semantic_mcp_api.py`, TC-18 | pass | `vector` → `embedding_unavailable` (generic text), `hybrid` → keyword results with `degraded: true`, `search_articles` unaffected |
| AC-11 mixed models | TC-12, TC-22 `test_embedder_db.py`, `test_semantic_repo.py`, `test_semantic_mcp_api.py` | pass | other-model rows never matched by vector; the worker clears them at start (also with Ollama down) and re-embeds them. Covered as parts plus the tool, not as one combined test |
| AC-12 auth and limit | TC-13 `test_semantic_mcp_api.py` | pass | no key and a revoked key refused; the per-minute limit applies to the tool. The limit test makes up to 10 tool calls against a limit of 8 requests/minute and passes whether or not a minute boundary resets the window, but depends on that behaviour |
| AC-13 retention | TC-14 `test_embedding_retention.py` | pass | the old embedded row is deleted with its vector, the fresh one keeps it |
| AC-14 measured baseline | TC-15 `test_search_eval.py` | pass (automatic part) | harness prints recall@5 and MRR for four methods. TC-16 (the owner reads the numbers) is **pending the owner**; numbers in §3 |
| AC-15 config external | TC-17 `test_config.py`, `test_semantic_config.py`, `make config-python` | pass | env > file > default for the worker and the API; no tunable literal in code |

## 3. Measurements (provisional targets; they do not fail the milestone)

Real data: 99,401 articles from the dev database (it keeps ingesting, so earlier runs saw 64–67k), `nomic-embed-text`, this machine. "Before" is the worker as first built.

| What | Measured |
|---|---|
| Embedding throughput, model alone | 205 titles/s (spike, batches of 32 and 256) |
| **Backfill, worker end to end** | **after the fix: 99,401 rows in 17.7 min, 93.5 rows/s overall, 100 rows/s in the first quarter and 88 rows/s in the last (flat).** Before: 67,191 rows in 24.8 min, 101 rows/s falling to 22 rows/s |
| Backfill of a full 350k window | not measured at that size; at the flat ~90 rows/s about 65 minutes **[estimate]** (the HNSW index was already 393 MB, three times the default `shared_buffers`, without slowing the rate) |
| Cost of picking the next batch (real 67k rows) | before: 1.8 ms with none embedded, 7 ms at 10k, 20 ms at 30k, ~100 ms at 60k, and 78 ms for every idle poll when all were embedded; with the partial index 0.7 ms at any size |
| Table and index size at 99,401 rows | total 1,008 MB: heap 130 MB, TOAST (vectors) 412 MB, HNSW 393 MB (3,958 bytes per row), full-text GIN 10.8 MB |
| Extrapolated to 350k rows | HNSW ≈ 1.4 GB, total ≈ 3.6 GB (R-1 said ≈ 2.8 GB) |
| `semantic_search` latency (100 real queries, quiet machine) | hybrid end to end p50 25 ms, p95 31 ms; vector end to end p50 21 ms, p95 26 ms. Parts: embedding the query p50 12 ms / p95 16 ms; vector leg SQL p50 8.0 / p95 11.4 ms (same with a selective domain filter); keyword leg SQL p50 2.8 / p95 3.3 ms |
| Does Postgres use the HNSW index with the repo's own SQL? | yes at 99k rows (`Index Scan using ix_articles_embedding_hnsw`, 50 rows) |
| Approximate vs exact top-10 (40 queries, `ef_search` 100) | by distance 0.990 mean (min 0.8); by id 0.95 (ids tie: 3,499 of 99,401 rows share a title with another row, so exact neighbours tie in distance) |
| recall@5 / MRR on the 40-title eval set (real model) | keyword substring 0.028 / 0.083; full-text 0.153 / 0.250; vector 1.000 / 1.000; hybrid 1.000 / 1.000; identical with and without prefixes. **Too easy to choose between vector and hybrid or to tune `semantic_rrf_k`, `semantic_candidates` or the prefixes** |
| Effect of `semantic_rrf_k` and `semantic_candidates` | not measured (the eval saturates) |

What real queries return (qualitative, 8 queries, titles only, measured at 67k rows): vector and hybrid find what the substring search cannot ("ceasefire talks" → Ukraine ceasefire items, "earthquake damage" → quake reports, "tech company layoffs" → layoff stories; the substring search returned nothing for 7 of 8). Quality is good but not perfect for a title-only index: "wildfire evacuation" returns wildfire items that are not about evacuations, and hybrid for "oil prices falling" puts "Sensex Falls Slightly as Oil Prices Rise…" second because a keyword hit counts as much as a vector hit under reciprocal-rank fusion.

## 4. Findings

| ID | Severity | Finding | Decision |
|---|---|---|---|
| F-1 | P1 | **The worker's batch query scanned past every already-embedded row** (`ORDER BY seq DESC` with a "not embedded" filter; the newest rows are the ones just embedded). Cost grew with the table (numbers in §3) and each idle poll was a 78 ms full scan at 67k rows. | **Fixed (T-10, D-9):** migration 0009 adds the partial index `ix_articles_unembedded (seq) WHERE embedding IS NULL`; the worker's queue is `embedding IS NULL`, and vectors of another model are cleared once at worker start so they join it. Tests TC-21 (plan uses the index) and TC-22 (clearing, also with Ollama down); re-measured: flat 88–100 rows/s |
| F-2 | — | The backfill slowdown (101 → 22 rows/s) was thought to come from per-row commits, the HNSW index outgrowing `shared_buffers` and non-heap-only updates. **The re-measurement shows F-1 was all of it:** the rate stays flat with a 393 MB index. The worker still runs at ~90–100 rows/s, below the model's 205 titles/s; committing once per batch could add some | resolved by F-1; batch commits are an optional P3 |
| F-3 | P2 | R-1 revised: a full 7-day window needs ≈ 3.6 GB (HNSW ≈ 1.4 GB), not ≈ 2.8 GB. `halfvec` stays the fallback | recorded |
| F-4 | P3 | The worker logs two INFO lines per batch (its own plus `httpx`'s per-request line): 6,216 lines for 99k rows. Set the `httpx` logger to WARNING | backlog |
| F-5 | P2 | The eval set cannot discriminate (recall and MRR 1.0 for vector and hybrid) | already in backlog ("Harder search eval") |
| F-6 | P3 | Hybrid weighs a keyword hit as much as a vector hit; noisy keyword matches can displace good vector results (§3, "oil prices falling") | belongs to the harder eval (F-5) |
| F-7 | — | **Incident, not a feature defect:** while implementing, my Docker test runs wiped most of the dev database's articles (old test modules used the dev stack's port because `docker compose up --wait` exits 0 on a port clash). Recovered by replaying Kafka `gkg.clean`; the tests now use throwaway databases and fixed-port modules are guarded (commit `f2518c6`). Lost for good: the demo agent's analyses and old slot history | fixed, memory saved |
| F-8 | — | Migration 0009 has **not** been applied to the dev database (still `0008`); the dev stack's compose has no `embedder` service | the owner runs `make migrate` when they start the embedder |

**Measurement harness notes (for the record):** my first backfill run reported a "stall" at 14,336 rows. It was a bug in my script (the worker's output pipe was never read and filled up), not in the embedder. Separately, one Docker run during this verify executed nothing because my shell was in the wrong directory (pytest said `file or directory not found`); I caught it from the output and reran it from the repo root, so the 214 passed above is a real run.

## 5. Doc drift and scope

- **Fixed:** `design.md` and `design-detail.md` named `_apply_filters` (now the public `apply_filters`) and described the old batch query (now the partial-index queue and the start-up clearing); `tests.md` described an HTTP stub server that was never needed and now lists TC-21, TC-22; `tasks/T-07.md` named the test seam `embedder=` (it is `query_embedder=`); ADR-0024 and CLAUDE.md describe the queue. Names agree across code and docs for `semantic_search`, `embedding`, `embedding_model`, migrations `0008`/`0009`, `ix_articles_unembedded`, `embedder`, `embedder_rw`, the `semantic_*`/`embedding_*` settings and the error codes.
- **ADRs:** ADR-0024 (queue and model changes) and ADR-0025 are accurate; the prefix question is recorded in `spike.md`.
- **Scope:** nothing from `backlog.md` was implemented (no REST route, UI, body extraction, re-ranking, `halfvec`, `similar_to`). Small additions beyond the spec, all recorded: the `embedder_rw` role, `newsdock_db.testing` and `newsdock_embedding.testing` (test support), full-text and MRR rows in the eval, the Docker-test safety work of F-7, and D-9 with migration 0009.
- **README/run instructions:** `ollama pull nomic-embed-text` and the nine-service note are in place. A clean-state `make up` from the README was not run (it would use the dev stack).

## 6. Follow-ups

1. Run the Kafka modules and the whole-stack scripts once with the dev stack stopped (open since two earlier verifies); that also exercises the `embedder` compose service and the `0009` head check.
2. Harder search eval (F-5/F-6), then choose the prefix setting, `semantic_rrf_k` and `semantic_candidates` from numbers.
3. P3: quiet the `httpx` log (F-4); optionally commit once per batch (F-2).
4. The owner reads the eval numbers in §3 (AC-14, TC-16).
5. `make migrate` on the dev database and an `embedder` service in the dev compose when the owner wants semantic search on live data.
