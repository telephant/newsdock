# semantic-search — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Article body extraction (P2, M3 part 2):** polite fetching and text extraction; legal review first. Prerequisite for embedding more than titles.
- **Events + Mentions streams (P2, M3 part 3):** CAMEO events and mentions linked to GKG.
- **REST route and UI search bar (P2):** `GET /api/articles/semantic` and a search box; the UI backlog already wants feed filters and search.
- **Fuzzy duplicate grouping (P2, from dedup-syndication):** group reworded duplicates by vector distance on top of the story key.
- **Chunked body embeddings (P3):** after body extraction.
- **Re-ranking (P3):** cross-encoder or LLM re-rank of the top results.
- **Embedding model comparison (P3):** run the AC-14 eval across models (and a hosted one, M6).
- **Similar articles for an article id (P3):** `similar_to(article_id)` MCP tool, no query embedding needed.
- **Embed `article_sources` copies (P3):** only if source-level search is needed.
- **Harder search eval (P2, found at T-08):** the 40-title, 8-topic set scores 1.000 recall@5 and MRR for vector and hybrid, so it cannot pick the prefix setting, `semantic_rrf_k` or `semantic_candidates`. Build a set with confusable topics (for example central-bank vs government-bond news, several wildfires, several elections), real GDELT titles from the 7-day window, and queries written by someone other than the label author.
