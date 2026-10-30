"""The rolling theme baseline (design.md §4, design-detail §3 and §6).

One entry per digest cycle: when it ran, how many articles it read and the count of
each non-generic theme. Pooling the entries gives a theme's usual share of the news,
which is what "rising" is measured against.
"""

from collections.abc import Mapping
from datetime import datetime

from pydantic import BaseModel


class BaselineEntry(BaseModel):
    at: datetime
    articles: int
    themes: dict[str, int]


class Baseline(BaseModel):
    version: int = 1
    entries: list[BaselineEntry] = []

    def is_warm(self, min_entries: int) -> bool:
        return len(self.entries) >= min_entries

    @property
    def latest_at(self) -> datetime | None:
        return self.entries[-1].at if self.entries else None

    def append(self, entry: BaselineEntry, *, keep: int) -> "Baseline":
        """A new baseline with `entry` added and only the newest `keep` entries."""
        entries = [*self.entries, entry]
        return Baseline(version=self.version, entries=entries[-keep:] if keep else [])

    def share(self, theme: str) -> float:
        """The theme's pooled count over the pooled article count (0.0 if unknown)."""
        articles = sum(e.articles for e in self.entries)
        if articles <= 0:
            return 0.0
        return sum(e.themes.get(theme, 0) for e in self.entries) / articles


def entry_from_counts(
    at: datetime,
    articles: int,
    counts: Mapping[str, int],
    *,
    skip_prefixes: tuple[str, ...],
    themes_kept: int,
) -> BaselineEntry:
    """Keep the `themes_kept` largest non-skip-listed themes with count >= 2."""
    kept = sorted(
        (
            (code, n)
            for code, n in counts.items()
            if n >= 2 and not code.startswith(skip_prefixes)
        ),
        key=lambda item: (-item[1], item[0]),
    )[:themes_kept]
    return BaselineEntry(at=at, articles=articles, themes=dict(kept))
