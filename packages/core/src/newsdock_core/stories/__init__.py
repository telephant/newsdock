"""Story key: groups syndicated copies of one story (ADR-0012, C-10).

Pure and deterministic: NFKC → lowercase → collapse whitespace → fixpoint-strip
a trailing ``| Site`` / ``- Site`` segment. Stripping runs to a fixpoint so
``"T"``, ``"T | SiteA"`` and ``"T - Part | SiteB"`` converge to the same key.
The thresholds keep real in-title dashes: strip only when the remainder keeps
at least MIN_REMAINDER chars and the segment is at most MAX_SEGMENT chars.
"""

import re
import unicodedata

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
