# newsdock-embedding

Shared Ollama embedding code (`newsdock_embedding`, ADR-0024), used by the embedder worker and the API so documents and queries are embedded the same way.

- `embed(texts, model=, url=, timeout=, client=None)` posts `{"model", "input": [...]}` to `{url}/api/embed` and returns one vector per text. An empty list sends nothing.
- `document_text(title, prefix)` and `query_text(query, prefix)` apply the task prefix (configurable, `nomic-embed-text` expects `search_document: ` / `search_query: `).
- `validate(vector, dimension)` rejects a wrong length or a non-finite value with `BadEmbedding`.
- Connection errors, timeouts, HTTP errors (including a model that is not pulled: 404) and bodies without embeddings raise `OllamaUnavailable`.
- `newsdock_embedding.testing.FakeOllama` is a deterministic `httpx.MockTransport` fake for tests.
- No environment reads, no app, `newsdock_core` or `newsdock_db` import; `domain/` code never imports this package (adapters do).

Test: `uv run pytest packages/embedding`.
