"""Ollama summariser: one plain-prose `/api/chat` call per theme (C-55).

Unlike the scorer there is no JSON schema; the model writes one sentence. Whatever
goes wrong (Ollama down, slow, an error status, an empty or odd answer) the result is
`None`, so a section shows "Summary unavailable." and the digest is still written.
"""

import logging
import re
from collections.abc import Sequence
from typing import Any

import httpx

from newsdock_agent.domain.prompt import theme_prompt

logger = logging.getLogger(__name__)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_MARKER = re.compile(r"^(?:[-*•]|\d+[.)])\s+")
_QUOTES = "\"'`“”‘’"


def clean_answer(raw: str, max_chars: int) -> str | None:
    """The first real line of the answer: no think block, list marker or quotes."""
    for line in _THINK.sub("", raw).splitlines():
        line = _MARKER.sub("", line.strip()).strip().strip(_QUOTES).strip()
        if not any(ch.isalnum() for ch in line):
            continue
        if len(line) > max_chars:
            line = line[: max_chars - 1].rstrip() + "…"
        return line
    return None


class OllamaSummariser:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_seconds: float,
        temperature: float,
        max_chars: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_chars = max_chars
        self._client = httpx.Client(
            base_url=base_url, timeout=timeout_seconds, transport=transport
        )

    def summarise(self, label: str, titles: Sequence[str]) -> str | None:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": theme_prompt(label, titles)}],
            "stream": False,
            "options": {"temperature": self._temperature},
        }
        try:
            response = self._client.post("/api/chat", json=body)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("no summary for %s: %s", label, type(exc).__name__)
            return None
        message = data.get("message") if isinstance(data, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            return None
        return clean_answer(content, self._max_chars)
