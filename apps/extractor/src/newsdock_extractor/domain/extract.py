"""Main text out of an HTML page (design-detail.md section 5).

`trafilatura` is a pure computation over a string (no I/O), so it lives here; it is
CPU-bound, so the caller runs `extract_text` in a worker thread. The result is plain
text with one paragraph per line.
"""

from dataclasses import dataclass

import trafilatura

from newsdock_extractor.domain.status import BodyStatus


@dataclass(frozen=True)
class ExtractResult:
    status: BodyStatus  # `ok` or `no_text`
    text: str | None  # None unless `ok`


def extract_text(
    html: str, url: str, *, min_chars: int, text_cap_chars: int
) -> ExtractResult:
    """The cleaned, capped main text of `html`, or `no_text`. Never raises."""
    try:
        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            include_links=False,
            include_images=False,
            favor_precision=False,
            output_format="txt",
        )
    except Exception:  # noqa: BLE001  a parser failure must not stop the worker
        return ExtractResult(BodyStatus.no_text, None)
    text = (extracted or "").strip()
    if len(text) < min_chars:
        return ExtractResult(BodyStatus.no_text, None)
    return ExtractResult(BodyStatus.ok, cap_text(text, text_cap_chars))


def cap_text(text: str, cap: int) -> str:
    """At most `cap` characters, cut at the last whole paragraph that fits.

    A first paragraph that alone exceeds the cap is cut at the last space (or hard,
    when it has none) so a word is never split.
    """
    if len(text) <= cap:
        return text
    kept: list[str] = []
    size = 0
    for paragraph in text.split("\n"):
        added = len(paragraph) + (1 if kept else 0)
        if size + added > cap:
            break
        kept.append(paragraph)
        size += added
    if kept:
        return "\n".join(kept)
    head = text[:cap]
    cut = head.rfind(" ")
    return (head[:cut] if cut > 0 else head).rstrip()
