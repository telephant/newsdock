"""The one Ollama `/api/embed` client (ADR-0024)."""

from typing import Any

import httpx

from newsdock_embedding.errors import BadEmbedding, OllamaUnavailable

_BODY_LIMIT = 200


def _clip(text: str) -> str:
    return text if len(text) <= _BODY_LIMIT else text[:_BODY_LIMIT] + "..."


def embed(
    texts: list[str],
    *,
    model: str,
    url: str,
    timeout: float,
    client: httpx.Client | None = None,
) -> list[list[float]]:
    """Embed `texts` in one request; the result has one vector per text, in order.

    Sends no request for an empty list. Pass `client` to reuse a connection.
    """
    if not texts:
        return []
    endpoint = url.rstrip("/") + "/api/embed"
    payload = {"model": model, "input": texts}
    try:
        if client is None:
            with httpx.Client(timeout=timeout) as own:
                response = own.post(endpoint, json=payload)
        else:
            response = client.post(endpoint, json=payload, timeout=timeout)
    except httpx.HTTPError as exc:
        raise OllamaUnavailable(
            f"ollama request failed: {exc.__class__.__name__}: {exc}"
        ) from exc
    if response.status_code != 200:
        raise OllamaUnavailable(
            f"ollama answered {response.status_code}: {_clip(response.text)}"
        )
    try:
        body: Any = response.json()
        vectors = body["embeddings"]
    except (ValueError, KeyError, TypeError) as exc:
        raise OllamaUnavailable(
            "ollama answered with a body that has no embeddings"
        ) from exc
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        got = len(vectors) if isinstance(vectors, list) else "none"
        raise BadEmbedding(f"expected {len(texts)} vectors, got {got}")
    return [[float(value) for value in vector] for vector in vectors]
