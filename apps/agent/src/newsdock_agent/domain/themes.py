"""Theme counting and ranking (design-detail §3). Pure: no I/O.

`rise` is the window count divided by what the baseline predicts for a window of this
size (pooled share x articles read), floored at 1 so a brand-new theme gets its own
count instead of infinity. Before the baseline is warm, themes rank by plain count.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from newsdock_agent.domain.articles import Article
from newsdock_agent.domain.baseline import Baseline


@dataclass(frozen=True)
class RankedTheme:
    code: str
    count: int
    rise: float | None  # None = no baseline yet


def count_themes(articles: Iterable[Article]) -> dict[str, int]:
    """Articles per theme; a theme counts once per article."""
    counts: Counter[str] = Counter()
    for article in articles:
        counts.update(set(article.themes))
    return dict(counts)


def rank_themes(
    counts: Mapping[str, int],
    window_articles: int,
    baseline: Baseline,
    *,
    skip_prefixes: tuple[str, ...],
    min_count: int,
    max_themes: int,
    min_entries: int,
) -> list[RankedTheme]:
    eligible = {
        code: n
        for code, n in counts.items()
        if n >= min_count and not code.startswith(skip_prefixes)
    }
    pooled_articles = sum(e.articles for e in baseline.entries)
    warm = baseline.is_warm(min_entries) and pooled_articles > 0
    if not warm:
        ordered = sorted(eligible.items(), key=lambda item: (-item[1], item[0]))
        return [RankedTheme(code, n, None) for code, n in ordered[:max_themes]]
    ranked = [
        RankedTheme(
            code,
            n,
            n / max(baseline.share(code) * window_articles, 1.0),
        )
        for code, n in eligible.items()
    ]
    ranked.sort(key=lambda r: (-(r.rise or 0.0), -r.count, r.code))
    return ranked[:max_themes]
