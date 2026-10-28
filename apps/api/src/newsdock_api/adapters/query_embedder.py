"""Ollama access for queries: the QueryEmbedder port over `newsdock_embedding`."""

import httpx
from newsdock_embedding import (
    BadEmbedding,
    OllamaUnavailable,
    embed,
    query_text,
    validate,
)

from newsdock_api.domain.semantic import EmbeddingUnavailable


class OllamaQueryEmbedder:
    def __init__(
        self,
        *,
        url: str,
        model: str,
        dimension: int,
        prefix: str,
        timeout: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = url
        self._model = model
        self._dimension = dimension
        self._prefix = prefix
        self._timeout = timeout
        self._client = client

    def embed_query(self, query: str) -> list[float]:
        try:
            (vector,) = embed(
                [query_text(query, self._prefix)],
                model=self._model,
                url=self._url,
                timeout=self._timeout,
                client=self._client,
            )
            validate(vector, self._dimension)
        except (OllamaUnavailable, BadEmbedding) as exc:
            raise EmbeddingUnavailable(str(exc)) from exc
        return vector
