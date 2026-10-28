"""Ollama access: the worker's DocumentEmbedder port over `newsdock_embedding`."""

import logging

import httpx
from newsdock_embedding import (
    BadEmbedding,
    OllamaUnavailable,
    document_text,
    embed,
    validate,
)

from newsdock_embedder.domain.loop import EmbedderUnavailable

logger = logging.getLogger(__name__)


class OllamaDocumentEmbedder:
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

    def embed_documents(self, titles: list[str]) -> list[list[float] | None]:
        texts = [document_text(title, self._prefix) for title in titles]
        try:
            vectors = embed(
                texts,
                model=self._model,
                url=self._url,
                timeout=self._timeout,
                client=self._client,
            )
        except (OllamaUnavailable, BadEmbedding) as exc:
            raise EmbedderUnavailable(str(exc)) from exc
        checked: list[list[float] | None] = []
        for vector in vectors:
            try:
                validate(vector, self._dimension)
                checked.append(vector)
            except BadEmbedding as exc:
                logger.warning("rejected a vector: %s", exc)
                checked.append(None)
        return checked
