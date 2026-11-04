# ADR-0036: Bodies and passages tables, `halfvec` vectors, and a discovery queue

Status: **Accepted 2026-11-02** (spec `body-extraction`, D-1, D-2, D-6; confirmed by the user during `/spec-design`)

Amended **2026-11-04** (approved by the user): the passage pass is **opt-in** — `embedder.embed_passages`, default off. The pass is most of the embedder's compute and vector storage (several vectors per article against one title, continuous HNSW churn under 7-day retention), while `scope=body|all` has no measured retrieval win yet (the search evals grade titles only). Until the backlog's body-scope evaluation shows passage vectors beat the passages' GIN keyword leg, `body` and `all` searches lean on that keyword leg; vectors already stored stay until retention removes them, and turning the flag on resumes decision (a) unchanged.

## Context
Every canonical article (50–75 k a day, **[assumption]**) gets a body; text is capped at 20,000 characters and kept 7 days. Ollama serves `nomic-embed-text` with a 2,048-token context, so one vector cannot cover an article: passages of about 1,000 characters are embedded (measured 67–70 passages/s on this machine, **[verified]**). One `vector(768)` is about 3 KB; at roughly 4 passages per article, 7 days is 1.4–2.1 M passages. The embedder polls "vector IS NULL" through a partial index (ADR-0024); polling an anti-join over 500 k articles every few seconds would not scale. pgvector 0.8.7 (image) and `pgvector` 0.5.1 (Python) both support `halfvec`.

## Options
- **(a) `article_bodies` (status machine, queue by partial index) and `article_passages` (`halfvec(768)`, HNSW cosine, GIN full-text), both cascading from `articles`; pending rows created by the extractor's own discovery pass from `articles.seq`; passages split in the extractor and embedded by a second embedder pass.**
- **(b) Same tables, pending rows created by a trigger on `articles` or by the sink.** Simpler queue, but ingestion's transaction then depends on the new table.
- **(c) Same, full `vector(768)` passages.** Simplest types, twice the storage.
- **(d) One vector per body (first 2,048 tokens), no passages.** Smallest, but a long article's later text is invisible and no passage can be returned.

## Decision
**(a)**. Discovery: `INSERT ... SELECT FROM articles WHERE seq > max(article_bodies.seq)` in batches, starting from the last `backfill_hours` on an empty table (no back-fill of older articles). The queue is `status = 'pending' AND next_attempt_at <= now() AND created_at >= now() - retention` newest first. Passage vectors are `halfvec(768)` with `halfvec_cosine_ops`. Retention is the article's cascade (AC-8).

## Consequences
+ Cheap polling at any table size; ingestion, the sink and the trigger-free schema are untouched (AC-15).
+ About half the storage: measured in T-01, 4.9 KB per passage with `halfvec` against 9.4 KB with `vector`, text, HNSW and full-text index included, so 7 days is about 6–8.5 GB (11–16 GB with `vector`); the best passage per article can be returned (RAG).
+ Retention needs no new job.
− Discovery relies on `seq` order matching commit order, the same property as the platform's own cursor (one sink consumer).
− Pending rows older than the window linger until their article is deleted (harmless, never picked).
− `halfvec` rounds vectors to 16 bits; a small precision loss to check in the evaluation backlog. The first migration against a real database must be tried on a copy (HNSW build time).
− The embedder grows a second pass and a second repository; its Docker test scene must cover it.
