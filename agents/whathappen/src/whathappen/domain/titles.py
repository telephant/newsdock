"""Title cleaning, tokens and the "same event" rule (design-detail §2). Pure: no I/O.

Two headlines are judged to report one event by the significant words they share, with
no model and no embeddings. The rule was measured on real headlines (spike.md): it
merges rewordings of one event and keeps unrelated pairs apart. A title is first
cleaned (entities decoded, a trailing " | Outlet" dropped), then reduced to a set of
lowercase words: stop-words and very short words are dropped, plurals folded, and
long words cut to six characters so `hospitalized`, `hospitalised` and `hospital`
meet.
"""

import html
import re
from dataclasses import dataclass

from whathappen.domain.text import clean_text

_OUTLET_SEPARATOR = " | "
_OUTLET_MAX_CHARS = 60
_MIN_WORDS_BEFORE_SECOND_STRIP = 3
_NON_WORD = re.compile(r"[^a-z0-9\s'-]")
_STEM_CHARS = 6
_STOP_WORDS = frozenset(
    "a an the and or but of in on at to for from by with as is are was were be been "
    "being it its this that these those after before over under into out up down new "
    "says say said will would can could may might has have had not no yes more most "
    "about against between during via per than then so if when what who how why where "
    "which their his her he she they we you i us our your my".split()
)


def clean_title(title: str) -> str:
    """The title as shown and compared: entities decoded, whitespace flattened, and
    trailing " | Outlet" segments removed.

    A segment is the text after the last pipe, up to 60 characters, as long as
    something remains in front of it. Sites append one ("| WKZO") or two
    ("| Politics | News") of them; a second one goes only while at least three words
    remain, so a short headline such as "Letters | Opinion" is left whole."""
    text = clean_text(title)
    stripped = False
    while True:
        head, separator, tail = text.rpartition(_OUTLET_SEPARATOR)
        if not (separator and head and tail and len(tail) <= _OUTLET_MAX_CHARS):
            return text
        if stripped and len(head.split()) < _MIN_WORDS_BEFORE_SECOND_STRIP:
            return text
        text, stripped = head, True


def title_tokens(title: str) -> frozenset[str]:
    """The significant words of a title, as a set."""
    text = html.unescape(clean_title(title)).lower()
    text = _NON_WORD.sub(" ", text).replace("'s", "")
    tokens: set[str] = set()
    for word in text.split():
        word = word.strip("'-")
        if len(word) < 3 or word in _STOP_WORDS:
            continue
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
            word = word[:-1]
        tokens.add(word[:_STEM_CHARS])
    return frozenset(tokens)


@dataclass(frozen=True)
class MatchParams:
    """Thresholds of the rule; the defaults are the measured ones."""

    overlap: float = 0.75
    jaccard: float = 0.5
    min_shared: int = 3


def matches(a: frozenset[str], b: frozenset[str], params: MatchParams) -> bool:
    """True if enough words are shared by either measure.

    Overlap = shared / the smaller set (a short headline inside a longer one);
    Jaccard = shared / all words. Either one reaching its threshold is enough, but
    never with fewer than `min_shared` shared words."""
    shared = len(a & b)
    if shared < params.min_shared:
        return False
    return (
        shared / min(len(a), len(b)) >= params.overlap
        or shared / len(a | b) >= params.jaccard
    )
