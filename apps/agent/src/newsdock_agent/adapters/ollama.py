"""Ollama scorer: /api/chat with JSON-schema structured output (spike.md §2)."""

import logging

import httpx

from newsdock_agent.domain.score import OUTPUT_SCHEMA, PROMPT, Score, parse_score

logger = logging.getLogger(__name__)


class OllamaScorer:
    def __init__(
        self, base_url: str, model: str, timeout_seconds: float = 120.0
    ) -> None:
        self._model = model
        self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds)

    def score(self, title: str) -> Score | None:
        response = self._client.post(
            "/api/chat",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": PROMPT.format(title=title)}],
                "format": OUTPUT_SCHEMA,
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
        return parse_score(content)
