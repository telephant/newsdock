"""Split a body into passages for embedding (design-detail.md section 5).

Whole paragraphs are packed until adding the next one would pass `target` characters;
a paragraph longer than `hard_max` is split first, at sentence ends, then at spaces,
then hard. No overlap (a tuning item for the evaluation backlog). Sizes count
characters, not bytes. Pure: the standard library only.
"""

import re

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_passages(text: str, *, target: int = 1000, hard_max: int = 1200) -> list[str]:
    """Passages in order, each at most `hard_max` characters, paragraphs joined by a
    newline. Empty text gives no passages."""
    if target < 1 or hard_max < target:
        raise ValueError("need 1 <= target <= hard_max")
    passages: list[str] = []
    current = ""
    for paragraph in (line.strip() for line in text.split("\n")):
        if not paragraph:
            continue
        for piece in _pieces(paragraph, target, hard_max):
            if current and len(current) + 1 + len(piece) > target:
                passages.append(current)
                current = piece
            else:
                current = f"{current}\n{piece}" if current else piece
    if current:
        passages.append(current)
    return passages


def _pieces(paragraph: str, target: int, hard_max: int) -> list[str]:
    """The paragraph whole if it fits, else cut into pieces of at most `hard_max`."""
    pieces: list[str] = []
    rest = paragraph
    while len(rest) > hard_max:
        cut = _cut_point(rest, target, hard_max)
        pieces.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        pieces.append(rest)
    return pieces


def _cut_point(text: str, target: int, hard_max: int) -> int:
    """Where to cut a text longer than `hard_max`: the last sentence end up to
    `target`, else up to `hard_max`, else the last space, else `hard_max`."""
    window = text[: hard_max + 1]
    ends = [m.start() for m in _SENTENCE_END.finditer(window)]
    within_target = [e for e in ends if e + 1 <= target]
    if within_target:
        return within_target[-1] + 1
    within_max = [e for e in ends if e + 1 <= hard_max]
    if within_max:
        return within_max[-1] + 1
    space = window.rfind(" ", 0, hard_max + 1)
    if space > 0:
        return space
    return hard_max
