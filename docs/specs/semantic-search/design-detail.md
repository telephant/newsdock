# semantic-search — Design detail

Reference only; not required reading for approval. Overview: [design.md](design.md).

## 1. Schema (migration `0008_article_embeddings`, head after `0007`)

```sql
ALTER TABLE articles ADD COLUMN embedding vector(768);
ALTER TABLE articles ADD COLUMN embedding_model text;
CREATE INDEX ix_articles_embedding_hnsw ON articles
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX ix_articles_title_fts ON articles
  USING gin (to_tsvector('english', title));
```

- Both columns nullable, so the migration is metadata-only and every existing row is unchanged (AC-1). Forward-only (DR-11): there is no downgrade.
- Role `embedder_rw` (NOLOGIN, like the other service roles): `SELECT` on `articles` and `UPDATE (embedding, embedding_model)`; no insert, no delete, no update of any other column.
- Rows with `embedding IS NULL` are not in the HNSW index.
- Alembic runs the extension-dependent DDL through `op.execute`; the ORM model gets `Vector(768)` from the `pgvector` package.

## 2. Embedder loop (C-35)

```
loop:
  rows = SELECT url_hash, title FROM articles
         WHERE embedding IS NULL OR embedding_model IS DISTINCT FROM :model
         ORDER BY seq DESC LIMIT :batch
  if no rows: heartbeat; sleep poll_interval_seconds; continue  # AC-3: no request sent
  try: vectors = embed_documents([title...])                    # C-36, one /api/embed call
  except OllamaError: log; heartbeat; sleep backoff; continue   # AC-4
  for (hash, vec) in zip(rows, vectors):
     if len(vec) != dimension or not finite: log; skip
     UPDATE articles SET embedding=:v, embedding_model=:model
      WHERE url_hash=:h AND (embedding IS NULL OR embedding_model IS DISTINCT FROM :model)
  heartbeat
```

- Newest first, so fresh articles become searchable before the backfill reaches old ones.
- A row whose vector keeps being rejected would be selected forever; the batch moves on only because newer rows sort first. Plan T-0x adds a bounded skip (`embed_failures` counter in memory per process) so one bad title cannot stall the head of the queue.
- Domain (`domain/`): batch selection rules and the "needs embedding" predicate as pure functions; adapters: SQL and Ollama.
- Healthcheck follows ADR-0015: the worker writes its allowed heartbeat age, setting `heartbeat_max_age_seconds` (360), which must exceed one worst-case loop (`ollama_timeout_seconds` + `backoff_max_seconds` = 120). The heartbeat is written after every pass, also while Ollama or the database is down, because restarting the worker would not fix either.

## 3. Embedding package (C-36)

- `embed(texts: list[str], *, model, url, timeout) -> list[list[float]]` = `POST {url}/api/embed {"model", "input": [...]}`, reads `embeddings` **[verified: Ollama API docs]**. `truncate` stays at its default (true); titles are far below the 2K context **[memory]**.
- `document_text(title, prefix)` and `query_text(query, prefix)`; prefixes come from settings.
- `validate(vector, dimension)`: right length, all finite.
- Errors: `OllamaUnavailable` (connect/timeout/5xx/model missing), `BadEmbedding` (length or NaN). No other I/O in the package.

## 4. Query SQL (C-37)

Vector leg (inside one transaction):

```sql
SET LOCAL hnsw.iterative_scan = relaxed_order;
SET LOCAL hnsw.ef_search = :ef;
SELECT url_hash, 1 - (embedding <=> :q) AS similarity
FROM articles
WHERE embedding_model = :model AND <_apply_filters>
ORDER BY embedding <=> :q
LIMIT :candidates;
```

`relaxed_order` can return slightly out-of-order rows, so the leg re-sorts by similarity in the outer query. `<=>` is cosine distance, similarity is `1 - distance` (range -1…1, AC-6).

Keyword leg:

```sql
SELECT url_hash, ts_rank(to_tsvector('english', title), q) AS rank
FROM articles, websearch_to_tsquery('english', :query) q
WHERE to_tsvector('english', title) @@ q AND <_apply_filters>
ORDER BY rank DESC, published_at DESC, url_hash
LIMIT :candidates;
```

`websearch_to_tsquery` never raises on odd input. `english` stems and drops stop words; non-English titles match poorly, which is accepted (spec assumptions).

Fusion (pure): `score(id) = Σ over legs 1 / (rrf_k + rank_in_leg)`, ranks start at 1; sort by score, then `published_at`, then `url_hash`. Take `limit`, then load the summaries with the existing helpers (`_scores`, `_source_counts`).

`SET LOCAL` values are bound through `set_config(..., true)` to stay parameterized (CLAUDE.md: SQL parameterized).

## 5. Tool behaviour (C-38)

| Case | Result |
|---|---|
| `vector`, Ollama ok | vector leg only, `degraded: false` |
| `hybrid`, Ollama ok | both legs fused |
| `vector`, Ollama down or wrong dimension | ToolError `embedding_unavailable` |
| `hybrid`, Ollama down | keyword leg only, `degraded: true`, `matched_by: ["keyword"]` |
| empty or over-long `query` | ToolError `invalid_query` |
| no rows have embeddings yet | `vector` returns an empty list; `hybrid` returns the keyword leg (not flagged degraded) |

The tool is registered next to the other tools in `adapters/http.py`; auth and the per-agent rate limit run in the shared `/mcp` path **[assumption: confirmed by the AC-12 test in the plan]**.

## 6. Deployment

- Compose: new service `embedder` (profile `apps`, networks `data`, same `config-file` mount and `db-env` as the sink, `depends_on` postgres healthy and `migrate` completed). It also needs the host route to Ollama (the same mechanism the demo agent uses, `host.docker.internal`; the plan checks the exact compose lines).
- The API service gets the same Ollama route and `embedding_*` settings.
- The demo agent keeps no Postgres/Kafka route (AC-13 of the MVP) and is unchanged.
- `make embedder-*` helpers are optional; `make eval-search` runs the eval (C-40) and needs Ollama and a side database.

## 7. Capacity (arithmetic, not measured)

350,000 rows × 768 floats × 4 bytes ≈ 1.1 GB of raw vectors. Measured on 50,000 rows (spike.md): HNSW 195 MB, whole relation 400 MB, so about 1.4 GB of HNSW and about 2.8 GB in total at a full window **[extrapolated]**. Story dedup means fewer canonicals than rows. Worker speed: the model embeds about 205 titles/s but the HNSW insert costs about 7.5 ms a row, so the worker is index-bound at about 130 rows/s and a full backfill takes about 45 minutes **[estimate]**. Because `embedding` is indexed, each UPDATE is not heap-only and also writes the other indexes of `articles` (R-5). Fallbacks, in order: `halfvec(768)` (half the size, supported to 4,000 dimensions **[verified: pgvector README]**), a smaller `embedding_dimension`, or embedding only recent days.

## 8. Failure table (full)

| Failure | Detection | Result |
|---|---|---|
| Ollama connection refused/timeout | `OllamaUnavailable` | worker: backoff, rows untouched; query: per §5 |
| Model not pulled (HTTP error from Ollama) | `OllamaUnavailable` with body logged | as above; operator pulls the model |
| NaN/short vector | `validate` | row skipped, counter incremented, logged |
| DB error in the worker | exception from SQLAlchemy | log, backoff, next pass; no partial batch state |
| Concurrent model change mid-batch | UPDATE guard | stale write skipped |
| HNSW returns fewer than candidates under a selective filter | row count | iterative scan continues up to `hnsw.max_scan_tuples`; fewer rows only if the scan limit hits **[verified: README]** |
| Backfill slower than ingest | queue never empties | still newest first; fresh articles searchable; reported by the eval/logging (provisional target) |

## 9. Security

- The query string is only ever bound as a parameter or sent to Ollama as JSON; never concatenated into SQL.
- The Ollama URL is operator config, not user input (no SSRF surface); the tool accepts no URL.
- Article titles come from public feeds and are rendered by agents as data; nothing here executes them.
- `semantic_search` returns only what `search_articles` can already return.
