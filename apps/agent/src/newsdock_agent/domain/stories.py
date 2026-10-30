"""Story picking (design-detail §4). Pure: no I/O.

Themes are walked in rank order. Each takes its best stories that no earlier theme
took, so a widely covered story that carries many themes appears once, under the
highest-ranked one, and does not make every theme's prompt the same.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from newsdock_agent.domain.articles import Article
from newsdock_agent.domain.themes import RankedTheme


@dataclass(frozen=True)
class ThemePick:
    theme: RankedTheme
    shown: list[Article]  # the linked stories
    prompt_articles: list[Article]  # the theme's own stories sent to the model


def _best_first(article: Article) -> tuple[int, float, str]:
    return (
        -article.source_count,
        -article.published_at.timestamp(),
        article.article_id,
    )


def pick_stories(
    ranked: Sequence[RankedTheme],
    articles: Sequence[Article],
    per_theme: int,
    prompt_titles: int,
) -> list[ThemePick]:
    taken: set[str] = set()
    ordered = sorted(articles, key=_best_first)
    picks: list[ThemePick] = []
    for entry in ranked:
        own = [
            a for a in ordered if a.article_id not in taken and entry.code in a.themes
        ][:prompt_titles]
        taken.update(a.article_id for a in own)
        picks.append(ThemePick(entry, own[:per_theme], own))
    return picks
