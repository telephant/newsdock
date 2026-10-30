"""One digest cycle (design.md F-40, design-detail §2): read, rank, write, ack.

The order is the point: the digest file is written first, the cursor is acked second
and the baseline saved last. A crash before the ack re-reads the same window (a
second, harmless file); a crash after it loses one baseline entry (a cache). The
model only writes prose: Python counts, ranks and picks, and a failed summary
degrades one section, never the digest.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from newsdock_agent.domain.articles import Article
from newsdock_agent.domain.baseline import Baseline, entry_from_counts
from newsdock_agent.domain.render import render_digest, theme_label
from newsdock_agent.domain.stories import pick_stories
from newsdock_agent.domain.themes import count_themes, rank_themes

logger = logging.getLogger(__name__)


class DigestMcpPort(Protocol):
    def list_new_articles(
        self, limit: int, cursor: str | None = None
    ) -> tuple[list[dict[str, object]], str]: ...

    def ack_cursor(self, cursor: str) -> None: ...


class SummaryPort(Protocol):
    def summarise(self, label: str, titles: Sequence[str]) -> str | None: ...


class DigestSinkPort(Protocol):
    def write(self, now: datetime, text: str) -> Path: ...


class BaselinePort(Protocol):
    def load(self) -> Baseline: ...

    def save(self, baseline: Baseline) -> None: ...


@dataclass(frozen=True)
class DigestParams:
    page_size: int
    max_articles: int
    skip_prefixes: tuple[str, ...]
    min_theme_count: int
    max_themes: int
    stories_per_theme: int
    prompt_titles: int
    baseline_hours: int
    baseline_min_entries: int
    themes_kept: int


@dataclass(frozen=True)
class Digest:
    text: str
    path: Path
    article_count: int
    cursor: str


class DigestCycle:
    def __init__(
        self,
        mcp: DigestMcpPort,
        summariser: SummaryPort,
        sink: DigestSinkPort,
        baseline_store: BaselinePort,
        params: DigestParams,
    ) -> None:
        self._mcp = mcp
        self._summariser = summariser
        self._sink = sink
        self._store = baseline_store
        self._params = params

    def run_once(self, now: datetime) -> Digest | None:
        """One cycle. Returns the digest, or None when there was nothing to write."""
        p = self._params
        baseline = self._store.load()
        articles, cursor, rows = self._read_window()
        if rows == 0:
            logger.info("empty window: no new articles, nothing written or acked")
            return None
        if not articles:
            logger.warning("%d rows were all unreadable: acking, no digest", rows)
            self._mcp.ack_cursor(cursor)
            return None

        counts = count_themes(articles)
        ranked = rank_themes(
            counts,
            len(articles),
            baseline,
            skip_prefixes=p.skip_prefixes,
            min_count=p.min_theme_count,
            max_themes=p.max_themes,
            min_entries=p.baseline_min_entries,
        )
        picks = pick_stories(ranked, articles, p.stories_per_theme, p.prompt_titles)
        summaries = {
            pick.theme.code: self._summarise(pick.theme.code, pick.prompt_articles)
            for pick in picks
            if pick.shown
        }
        text = render_digest(
            now=now,
            article_count=len(articles),
            since=baseline.latest_at,
            picks=picks,
            summaries=summaries,
        )

        path = self._sink.write(now, text)  # OSError here: no ack, window read again
        logger.info("digest written to %s\n%s", path, text)
        self._mcp.ack_cursor(cursor)
        self._remember(baseline, now, len(articles), counts)
        return Digest(text, path, len(articles), cursor)

    def _read_window(self) -> tuple[list[Article], str, int]:
        """Page until a short page or the cap; returns articles, last cursor, rows."""
        p = self._params
        articles: list[Article] = []
        cursor: str | None = None
        rows = 0
        while True:
            page, cursor = self._mcp.list_new_articles(p.page_size, cursor)
            rows += len(page)
            for item in page:
                try:
                    articles.append(Article.from_mcp(item))
                except ValidationError:
                    logger.warning("skipping an unreadable article row")
            if len(page) < p.page_size or rows >= p.max_articles:
                return articles, cursor, rows

    def _summarise(self, code: str, own: Sequence[Article]) -> str | None:
        try:
            return self._summariser.summarise(theme_label(code), [a.title for a in own])
        except Exception as exc:  # noqa: BLE001 - the model must never stop a digest
            logger.warning("summary for %s failed: %s", code, type(exc).__name__)
            return None

    def _remember(
        self,
        baseline: Baseline,
        now: datetime,
        article_count: int,
        counts: dict[str, int],
    ) -> None:
        p = self._params
        entry = entry_from_counts(
            now,
            article_count,
            counts,
            skip_prefixes=p.skip_prefixes,
            themes_kept=p.themes_kept,
        )
        try:
            self._store.save(baseline.append(entry, keep=p.baseline_hours))
        except OSError as exc:  # a cache: the digest and the ack already happened
            logger.warning("baseline not saved: %s", exc)
