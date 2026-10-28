"""The text recipe: documents and queries are embedded with their own prefix."""


def document_text(title: str, prefix: str) -> str:
    """The text embedded for a stored article title."""
    return f"{prefix}{title}"


def query_text(query: str, prefix: str) -> str:
    """The text embedded for a search query."""
    return f"{prefix}{query.strip()}"
