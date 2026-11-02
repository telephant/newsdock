"""Story groups and the grouper port (design C-72). Pure: no I/O.

A story group is a set of headlines judged to report one event. `StoryGrouper` is the
small interface the digest uses; `LexicalGrouper` is the implementation measured in
spike.md (word overlap, no model). Another grouper (for example platform clustering)
can replace it without touching the rest of the cycle.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from whathappen.domain.articles import Article
from whathappen.domain.titles import MatchParams, clean_title, matches, title_tokens


@dataclass(frozen=True)
class StoryGroup:
    """Headlines about one event. `members[0]` is the seed (the best-covered one)."""

    members: tuple[Article, ...]

    @property
    def seed(self) -> Article:
        return self.members[0]

    @property
    def sources(self) -> int:
        return sum(m.source_count for m in self.members)

    @property
    def shown(self) -> Article:
        """The headline to show: most sources, then newest."""
        return max(
            self.members,
            key=lambda m: (m.source_count, m.published_at, m.article_id),
        )

    @property
    def key(self) -> str:
        """A stable id for the group: its seed's article id."""
        return self.seed.article_id

    @property
    def variants(self) -> tuple[Article, ...]:
        """The distinct headlines, the shown one first, then best covered, newest.

        Two articles whose cleaned titles are equal (they differ only by an outlet
        suffix, say) are one headline; their coverage still counts in `sources`."""
        shown = self.shown
        others = [m for m in self.members if m.article_id != shown.article_id]
        others.sort(
            key=lambda m: (-m.source_count, -m.published_at.timestamp(), m.article_id)
        )
        seen: set[str] = set()
        variants: list[Article] = []
        for member in (shown, *others):
            cleaned = clean_title(member.title).casefold()
            if cleaned not in seen:
                seen.add(cleaned)
                variants.append(member)
        return tuple(variants)

    @property
    def also(self) -> tuple[Article, ...]:
        """The other distinct headlines (see `variants`)."""
        return self.variants[1:]

    @property
    def domains(self) -> frozenset[str]:
        return frozenset(m.domain for m in self.members if m.domain is not None)


class StoryGrouper(Protocol):
    def group(self, articles: Sequence[Article]) -> list[StoryGroup]: ...


class _Builder:
    def __init__(self, seed: Article, tokens: frozenset[str]) -> None:
        self.seed = seed
        self.tokens = tokens
        self.members = [seed]
        self.domains = {seed.domain} if seed.domain is not None else set()

    def add(self, article: Article) -> None:
        self.members.append(article)
        if article.domain is not None:
            self.domains.add(article.domain)


class LexicalGrouper:
    """Seed-based grouping by shared significant words.

    Articles are taken best covered first. Each joins the first group whose *seed* it
    matches (never another member, so one loose pair cannot chain groups together),
    provided it was published within `window` of that seed and its domain is not
    already in the group (an outlet does not report the same event twice, which also
    keeps template headlines from one site apart). Otherwise it starts a new group.
    A token index limits the comparison to groups that share a word with the article.
    """

    def __init__(self, params: MatchParams, window: timedelta) -> None:
        self._params = params
        self._window = window

    def group(self, articles: Sequence[Article]) -> list[StoryGroup]:
        order = sorted(
            articles,
            key=lambda a: (-a.source_count, a.published_at, a.article_id),
        )
        builders: list[_Builder] = []
        index: dict[str, list[int]] = defaultdict(list)
        for article in order:
            tokens = title_tokens(article.title)
            for position in self._candidates(tokens, index):
                builder = builders[position]
                if article.domain is not None and article.domain in builder.domains:
                    continue
                if abs(article.published_at - builder.seed.published_at) > self._window:
                    continue
                if matches(builder.tokens, tokens, self._params):
                    builder.add(article)
                    break
            else:
                builders.append(_Builder(article, tokens))
                for token in tokens:
                    index[token].append(len(builders) - 1)
        return [StoryGroup(tuple(b.members)) for b in builders]

    @staticmethod
    def _candidates(tokens: frozenset[str], index: dict[str, list[int]]) -> list[int]:
        """Groups sharing at least one word, in creation order."""
        found: set[int] = set()
        for token in tokens:
            found.update(index.get(token, ()))
        return sorted(found)
