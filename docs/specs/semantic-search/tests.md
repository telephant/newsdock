# semantic-search — Tests

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Plan: [plan.md](plan.md)

## Test data

- **Hand-made vectors.** Ranking, filter, model-mix and retention tests insert articles with explicit 768-dimension vectors (unit axes and small mixes), so distances are known and no model is needed. Helper `make_vec(*components)` pads to 768 with zeros. Lives in `apps/api/tests/integration/embedding_fixtures.py`; apps may not import each other's tests, so the embedder keeps its own two-line copy.
- **Fake Ollama.** A tiny in-process HTTP stub (`httpx.MockTransport` for unit tests, a `ThreadingHTTPServer` for integration) answering `POST /api/embed` with deterministic vectors derived from a hash of the text, a switch to fail (connection refused / HTTP 500 / wrong length / NaN) and a request counter. Lives in `packages/embedding/tests/fakes.py` and is re-exported by a test-only helper in each app that needs it.
- **Real model.** TC-7 and TC-16 need Ollama with `nomic-embed-text` and are marked `ollama` (not part of `make check`; run with `make eval-search`). Skipped with a clear message when Ollama is unreachable.
- **Eval corpus.** `apps/api/tests/eval/corpus.json` (about 40 hand-written, realistic news titles across 8 topics, some paraphrase pairs) and `queries.json` (about 12 natural-language queries with the ids that should match). Written by hand; no GDELT row is copied.
- **Docker Postgres.** Integration tests use the existing `side_db` fixture (pgvector image, own port) so they run beside a dev stack.

## Tests

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | integration | Given a database at head `0007` with articles, When `0008` is applied, Then `articles` has nullable `embedding` (vector 768) and `embedding_model`, an HNSW cosine index and a GIN index on `to_tsvector('english', title)`, and all earlier columns and rows are identical; the role `embedder_rw` may update only the two embedding columns; the ORM metadata matches the migration (no downgrade: migrations are forward-only, DR-11) |
| TC-2 | AC-2 | integration | Given a fake Ollama and one canonical article with no embedding, When the worker runs one pass, Then the row has a 768-dimension vector and `embedding_model` = the configured model |
| TC-3 | AC-3 | unit | Given a repo where nothing needs embedding and a counting embedder, When a pass runs, Then the embedder is called 0 times and no UPDATE is issued; a second pass over embedded rows behaves the same |
| TC-4 | AC-4 | integration | Given Ollama refusing connections, When the sink-style insert adds articles and the worker runs, Then the inserts exist, their embeddings stay NULL, a failure is logged, and after Ollama recovers the next pass embeds them |
| TC-5 | AC-5 | integration | Given 120 articles from before the migration and batch size 32, When the worker runs until a pass reports nothing left, Then all 120 are embedded, newest first |
| TC-6 | AC-6 | integration | Given three articles with known vectors at distances 0.1, 0.4, 0.9 from the query vector, When `semantic_search` runs with `mode=vector`, Then the order is ascending distance and each `score` equals 1 − distance within a small tolerance and lies in [−1, 1] |
| TC-7 | AC-7 | integration (`ollama`) | Given the real model and an article "Central bank lifts borrowing costs", When `semantic_search` (vector) and `search_articles` (text) are called with "interest rate hike", Then only the first returns it |
| TC-8 | AC-8 | unit | Given two ranked id lists, When RRF fuses them (k = 60), Then an id in both lists outranks ids in one list, ties break by `published_at` then `url_hash`, and an empty list leaves the other unchanged |
| TC-9 | AC-8 | integration | Given A in both legs, B only vector, C only keyword (hand-made vectors and titles), When `semantic_search` runs with `mode=hybrid`, Then A is first and B and C both appear with the right `matched_by` |
| TC-10 | AC-9 | integration | Given matches on several domains, themes (`ECON_INFLATION`, `ECON_TRADE`) and dates, When `semantic_search` is called with `domain`, `theme` (exact and `ECON_*`) and a time range, in both modes, Then only rows satisfying every given filter come back; with a selective filter fewer than `limit` rows still returns all that exist (iterative scan) |
| TC-11 | AC-10 | integration | Given an embedder that raises `OllamaUnavailable`, When `semantic_search` runs with `vector` and then `hybrid`, Then the first is a tool error `embedding_unavailable`, the second returns keyword results with `degraded: true`, and `search_articles` still returns normally |
| TC-12 | AC-11 | integration | Given rows embedded with model X and the configured model Y, When `semantic_search` runs and the worker runs a pass, Then X rows are absent from vector results before the pass, present again after (re-embedded with Y) |
| TC-13 | AC-12 | integration | Given auth required, When `semantic_search` is called without a key, with a revoked key, and past the per-minute limit, Then the first two are unauthorized and the third is rate limited, exactly as for `search_articles` |
| TC-14 | AC-13 | integration | Given an embedded article older than the retention window, When the sink retention pass runs (existing function), Then the row, with its embedding, is gone and `semantic_search` never returns it |
| TC-15 | AC-14 | integration | Given the eval corpus and a deterministic fake embedder, When the eval runs, Then it prints recall@5 for keyword, vector and hybrid and exits 0 |
| TC-16 | AC-14 | manual | Given the real model, When the owner runs `make eval-search`, Then the three recall@5 numbers are printed and the owner reads them (checklist below) |
| TC-17 | AC-15 | unit | Given `embedding_*`, `batch_size`, `poll_interval_seconds` and `semantic_*` set in the file and by env, When the settings load, Then the worker and the API read them (env over file over default); `common:` embedding keys reach both apps; an unknown key in a section is rejected |
| TC-18 | AC-2, AC-4, AC-10 | unit | Given an `httpx.MockTransport`, When the embedding client calls `/api/embed`, Then it sends `{"model", "input": [...]}` with the document or query prefix, parses `embeddings`, and maps connection error / timeout / HTTP 5xx / missing model to `OllamaUnavailable` and a short or non-finite vector to `BadEmbedding` |
| TC-19 | AC-4 | unit | Given a worker whose embedder always fails, When several passes run, Then the heartbeat file is refreshed every pass (alive, not stuck) and the backoff grows to its cap |
| TC-20 | AC-6 | unit | Given the tool's input handling, When `query` is empty, whitespace or longer than `semantic_query_max_length`, Then the tool raises `invalid_query` before any embedding call; `mode` outside {vector, hybrid} is rejected |

## Coverage

Every AC has at least one test: AC-1 TC-1 · AC-2 TC-2, TC-18 · AC-3 TC-3 · AC-4 TC-4, TC-18, TC-19 · AC-5 TC-5 · AC-6 TC-6, TC-20 · AC-7 TC-7 · AC-8 TC-8, TC-9 · AC-9 TC-10 · AC-10 TC-11, TC-18 · AC-11 TC-12 · AC-12 TC-13 · AC-13 TC-14 · AC-14 TC-15, TC-16 · AC-15 TC-17.

## Manual checklist (TC-7, TC-16; need Ollama with `nomic-embed-text`)

- [ ] `ollama list` shows `nomic-embed-text`; `curl` of `/api/embed` returns a 768-element vector (spike T-01 records it).
- [ ] `make eval-search` prints recall@5 for keyword, vector and hybrid and exits 0.
- [ ] Hybrid recall@5 is not lower than the keyword baseline on the corpus; if it is, record why in `verify.md` (no pass threshold, AC-14).
- [ ] The paraphrase case of TC-7 passes with the real model.

## Measurements (provisional targets, not pass/fail until real data exists)

| What | How |
|---|---|
| Embedding throughput (titles per second) | T-01 spike: time a batch of 32 and 256 real titles against the owner's Ollama |
| Backfill time for a full window | titles in window ÷ throughput; confirm on the live stack in `/spec-verify` |
| p95 `semantic_search` latency (vector and hybrid) | 100 calls on a populated database, report p50/p95 |
| Recall@5 keyword vs vector vs hybrid | `make eval-search` (TC-15/TC-16) |
| Table and index size at a full window | `pg_total_relation_size` and `pg_relation_size` of the HNSW index after backfill |
| Effect of `semantic_rrf_k` and `semantic_candidates` | rerun the eval with 20/60/100 and 30/50/100; record |
