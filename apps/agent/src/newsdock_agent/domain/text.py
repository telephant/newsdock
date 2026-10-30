"""Text cleaning for markdown output and prompts. Pure: no I/O.

Headline text is untrusted: it can hold HTML entities (real GDELT titles do), markup
characters, newlines or instructions aimed at the model. It is decoded once, flattened
to one line, and then either escaped as markdown text or passed on as plain text.
"""

import html
import re

_WHITESPACE = re.compile(r"\s+")
_MARKDOWN_SPECIAL = "\\[]`*_<>|&#~"
_URL_UNSAFE = {" ": "%20", "(": "%28", ")": "%29", "<": "%3C", ">": "%3E"}


def clean_text(text: str) -> str:
    """Decode HTML entities once, then collapse every whitespace run to one space."""
    return _WHITESPACE.sub(" ", html.unescape(text)).strip()


def escape_text(text: str) -> str:
    """Clean `text` and backslash-escape markdown syntax so it renders as itself."""
    cleaned = clean_text(text)
    return "".join("\\" + ch if ch in _MARKDOWN_SPECIAL else ch for ch in cleaned)


def encode_url(url: str) -> str:
    """Percent-encode the few characters that would end or break a markdown link."""
    flat = url.strip().translate({ord(c): None for c in "\r\n\t"})
    return "".join(_URL_UNSAFE.get(ch, ch) for ch in flat)
