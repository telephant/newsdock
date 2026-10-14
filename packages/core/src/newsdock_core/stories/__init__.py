"""Story key: groups syndicated copies of one story (ADR-0012, C-10).

Pure and deterministic: NFKC → lowercase → collapse whitespace → fixpoint-strip
a trailing ``| Site`` / ``- Site`` segment. Stripping runs to a fixpoint so
``"T"``, ``"T | SiteA"`` and ``"T - Part | SiteB"`` converge to the same key.
The thresholds keep real in-title dashes: strip only when the remainder keeps
at least MIN_REMAINDER chars and the segment is at most MAX_SEGMENT chars.
"""

import re
import unicodedata
from collections.abc import Sequence
from urllib.parse import parse_qsl, urlsplit

MIN_REMAINDER = 25
MAX_SEGMENT = 45
MAX_STRIP_ITERATIONS = 3

_SEPARATOR_RE = re.compile(r"\s+[|\-–—]\s+")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_suffix_once(title: str) -> str:
    matches = list(_SEPARATOR_RE.finditer(title))
    if not matches:
        return title
    last = matches[-1]
    remainder, segment = title[: last.start()], title[last.end() :]
    if len(remainder) >= MIN_REMAINDER and 1 <= len(segment) <= MAX_SEGMENT:
        return remainder
    return title


def story_key(title: str) -> str:
    """Grouping key for a headline; equal keys mean 'same story' (with the
    published_at window guard applied by the sink, D-5)."""
    key = unicodedata.normalize("NFKC", title).lower()
    key = _WHITESPACE_RE.sub(" ", key).strip()
    for _ in range(MAX_STRIP_ITERATIONS):
        stripped = _strip_suffix_once(key)
        if stripped == key:
            break
        key = stripped
    return key or _WHITESPACE_RE.sub(" ", title.lower()).strip()


def page_signature(url: str) -> tuple[str, str]:
    """Which page a URL points at, ignoring scheme, host, port, fragment and any
    path prefix: (last path segment lowercased, sorted query string).

    Station sites of one radio network share a slug under different hosts; two
    different pages of one site do not (ADR-0012 amendment 2026-10-09).
    """
    parts = urlsplit(url)
    segments = [seg for seg in parts.path.split("/") if seg]
    last = segments[-1].lower() if segments else ""
    query = "&".join(f"{k}={v}" for k, v in sorted(parse_qsl(parts.query)))
    return last, query


def can_join(
    domain: str | None, url: str, sources: Sequence[tuple[str | None, str]]
) -> bool:
    """May a copy join a story that already holds `sources` (domain, url)?

    Syndication means *other* sites carry the story, so a copy from a new domain
    always joins. A copy from a domain the story already has joins only when it is
    the same page (a host or scheme variant). Different pages of one site that share
    a generic title ("The Miami Student", "Subscribe to ...") must not merge: a
    missed grouping leaves a harmless duplicate, a false merge hides an article.
    """
    if domain is None:
        return True
    signature = page_signature(url)
    return all(
        source_domain != domain or page_signature(source_url) == signature
        for source_domain, source_url in sources
    )
