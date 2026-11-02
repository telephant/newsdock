"""Scoring story groups (design C-73, spec D-3). Pure: no I/O.

score = sources x (1 + tone_neg / tone_divisor)

`sources` is how many outlets carried the story (the platform's `source_count`, summed
over the group's headlines) and `tone_neg` is how negative it is (the largest value
among the group's articles; a missing value counts as 0). Coverage decides and
negative tone is a modest boost. If no article in the window has a tone value at all
(an older platform, or articles without tone) every score equals its source total and
the ranking is labelled "coverage".
"""

from collections.abc import Sequence
from dataclasses import dataclass

from whathappen.domain.grouping import StoryGroup

RANKING_COVERAGE = "coverage"
RANKING_TONE = "coverage and tone"


@dataclass(frozen=True)
class ScoredGroup:
    group: StoryGroup
    sources: int
    tone_neg: float | None  # None when none of the group's articles has a tone
    score: float


def _tone(group: StoryGroup) -> float | None:
    values = [m.tone_neg for m in group.members if m.tone_neg is not None]
    return max(values) if values else None


def score_groups(
    groups: Sequence[StoryGroup], tone_divisor: float
) -> tuple[list[ScoredGroup], str]:
    """The groups with their scores, best first, and which ranking was used."""
    if tone_divisor <= 0:
        raise ValueError("tone_divisor must be greater than 0")
    scored = []
    for group in groups:
        tone = _tone(group)
        sources = group.sources
        scored.append(
            ScoredGroup(
                group=group,
                sources=sources,
                tone_neg=tone,
                score=sources * (1 + (tone or 0.0) / tone_divisor),
            )
        )
    scored.sort(key=_order)
    has_tone = any(s.tone_neg is not None for s in scored)
    return scored, RANKING_TONE if has_tone else RANKING_COVERAGE


def _order(item: ScoredGroup) -> tuple[float, int, float, str]:
    """Best first: score, then sources, then newest, then the shown article's id."""
    newest = max(m.published_at for m in item.group.members)
    return (
        -item.score,
        -item.sources,
        -newest.timestamp(),
        item.group.shown.article_id,
    )
