"""Shared Ollama embedding client, text recipe and vector validation (ADR-0024).

No environment reads and no other I/O: callers pass the model, URL and timeout.
"""

from newsdock_embedding.client import embed
from newsdock_embedding.errors import BadEmbedding, OllamaUnavailable
from newsdock_embedding.text import document_text, query_text
from newsdock_embedding.vectors import validate

__all__ = [
    "BadEmbedding",
    "OllamaUnavailable",
    "document_text",
    "embed",
    "query_text",
    "validate",
]
