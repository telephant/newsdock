"""Errors of the embedding package; callers map them to their own outcomes."""


class OllamaUnavailable(Exception):
    """Ollama gave no embeddings: connection, timeout, HTTP error or a bad body."""


class BadEmbedding(Exception):
    """Ollama answered, but the vectors are unusable: wrong count, length or value."""
