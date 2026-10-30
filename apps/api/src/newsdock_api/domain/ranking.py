"""Reciprocal-rank fusion of ranked id lists (spec semantic-search AC-8, D-5).

Pure: no I/O, no settings. Each leg (for example `vector` and `keyword`) is a list
of hits, best first. An id's score is the sum over the legs that contain it of
`1 / (k + rank)`, ranks counted from 1, so raw scores from different scales are
never compared. Ties break by newest `published_at`, then by id, which keeps the
order stable.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Ranked:
    """One hit of one leg."""

    id: str
    published_at: datetime


@dataclass(frozen=True)
class Fused:
    """One article after fusion: its score and the legs that found it."""

    id: str
    score: float
    matched_by: tuple[str, ...]


def fuse(legs: Mapping[str, Sequence[Ranked]], *, k: int) -> list[Fused]:
    """Merge the legs into one ranking, best first.

    `legs` maps a leg name to its hits in rank order; the mapping order is the
    order of `matched_by`. A repeated id inside one leg counts once, at its first
    rank.
    """
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    published: dict[str, datetime] = {}
    for name, hits in legs.items():
        seen: set[str] = set()
        rank = 0
        for hit in hits:
            if hit.id in seen:
                continue
            seen.add(hit.id)
            rank += 1
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (k + rank)
            matched.setdefault(hit.id, []).append(name)
            published.setdefault(hit.id, hit.published_at)
    ordered = sorted(
        scores,
        key=lambda i: (-scores[i], -published[i].timestamp(), i),
    )
    return [Fused(i, scores[i], tuple(matched[i])) for i in ordered]
