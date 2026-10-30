# ADR-0025: Embeddings as columns on `articles`, HNSW cosine, full-text keyword leg

Status: **Accepted 2026-10-28** (recommended default taken on the user's `/loop finish M3 by using /spec-*` instruction; revisit if you object)

## Context
Spec `semantic-search` needs vector storage and search (D-7), a fixed vector size, a way to make model changes safe (AC-11), and a hybrid mode whose keyword side actually matches natural-language queries (D-5, D-8).

## Options
**Storage:** (a) `embedding` and `embedding_model` columns on `articles`; (b) a side table `article_embeddings(url_hash, model, embedding)` with `ON DELETE CASCADE`.
**Index:** (a) HNSW cosine; (b) IVFFlat; (c) none (exact scan).
**Keyword leg:** (a) `ILIKE '%query%'` as in `search_articles`; (b) Postgres full-text (`to_tsvector('english', title)` with a GIN index).
**Type:** `vector(768)` vs `halfvec(768)`.

## Decision
- **Columns on `articles`** (a). One row, one delete: retention removes the vector with no extra code (AC-13); the filters are on the same table. The cost is one UPDATE per row after insert; the NOTIFY trigger fires on INSERT only, so streams are not woken by it.
- **HNSW with `vector_cosine_ops`**, m 16, ef_construction 64, queried with `hnsw.iterative_scan = relaxed_order` so selective filters still return rows **[verified: pgvector 0.8 README]**. IVFFlat needs training data and re-clustering; an exact scan over ~350k rows is the fallback, not the plan.
- **`vector(768)`**, fixed by the migration. A same-dimension model swap needs no migration; a different dimension needs a new one. `embedding_model` makes mixed spaces safe: search only compares rows whose model equals the configured one.
- **Full-text keyword leg** (b). A natural-language query almost never appears as a substring of a title, so `ILIKE` would make hybrid collapse to vector. `websearch_to_tsquery` never errors on odd input. This amends AC-1 (extra index) and adds spec D-8.
- **Fusion by reciprocal rank (k = 60 as a starting point)**, so scores from two different scales never get compared.

## Consequences
+ Simple joins, one retention path, easy model swap. + Hybrid works on real queries.
− About 2.8 GB in total at a full window (HNSW about 1.4 GB), extrapolated from a 50,000-row spike **[extrapolated]**; `halfvec` halves the vectors and is the first fallback.
− Because `embedding` is indexed, each embedding UPDATE is not heap-only and also writes the other indexes of `articles`, and leaves one dead tuple for autovacuum (spike.md, R-5). A side table avoids this but breaks filtered search (iterative scan cannot see join filters), so the decision stands; measure the real backfill at verify.
− `english` stemming favours English titles.
− Switching to a side table later (to hold several models side by side, backlog) is a migration and a repo change.
− Adds the `pgvector` Python package to `newsdock_db` **[assumption]**.
