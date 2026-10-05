"""URL normalization and hashing; `url_hash` is the public article id."""

import hashlib
from urllib.parse import urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    """Lower-case scheme/host, strip fragment and trailing slashes, keep query."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


def url_hash(url: str) -> str:
    """sha256 hex of the normalized URL (dedup key and public article id)."""
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()
