"""One digest cycle (design.md F-70, design-detail §6): read, group, score, select,
write, ack.

The order is the point: the digest file is written first and the cursor acked second.
A crash before the ack re-reads the same window (a second, harmless file). The model
only writes prose, one sentence for a group of several headlines: Python groups,
scores and selects, and a failed sentence costs one line, never the digest.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from whathappen.domain.articles import Article
from whathappen.domain.grouping import StoryGroup, StoryGrouper
from whathappen.domain.render import render_story_digest
from whathappen.domain.scoring import score_groups
from whathappen.domain.sections import SectionLabels, SelectParams, select

logger = logging.getLogger(__name__)

TONE_INCLUDE = ["tone_neg"]  # the extra field asked of the platform (spec D-7)


def _clip(text: str, cap: int) -> str:
    """At most `cap` characters, cut at a word boundary."""
    if len(text) <= cap:
        return text
    head, _, _ = text[:cap].rpartition(" ")
    return (head or text[:cap]).rstrip() + "…"


class DigestMcpPort(Protocol):
    def list_new_articles(
        self,
        limit: int,
        cursor: str | None = None,
        include: Sequence[str] | None = None,
    ) -> tuple[list[dict[str, object]], str]: ...

    def get_article(self, article_id: str) -> Mapping[str, object]: ...

    def ack_cursor(self, cursor: str) -> None: ...


class SummaryPort(Protocol):
    def summarise(
        self, titles: Sequence[str], excerpt: str | None = None
    ) -> str | None: ...


class DigestSinkPort(Protocol):
    def write(self, now: datetime, text: str) -> Path: ...


@dataclass(frozen=True)
class DigestParams:
    page_size: int
    max_articles: int
    min_group_sources: int
    top_stories: int
    max_sections: int
    groups_per_section: int
    also_per_group: int
    section_min_hits: int
    tone_divisor: float
    labels: SectionLabels
    # Article text sent to the model per story (`get_article`'s stored `body`,
    # clipped); 0 = headlines only, exactly the digest before body grounding.
    summary_body_chars: int = 0
    body_lookups_per_group: int = 3  # distinct headlines asked for a body, per story


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
        grouper: StoryGrouper,
        summariser: SummaryPort,
        sink: DigestSinkPort,
        params: DigestParams,
    ) -> None:
        self._mcp = mcp
        self._grouper = grouper
        self._summariser = summariser
        self._sink = sink
        self._params = params

    def run_once(self, now: datetime) -> Digest | None:
        """One cycle. Returns the digest, or None when there was nothing to write."""
        p = self._params
        articles, cursor, rows = self._read_window()
        if rows == 0:
            logger.info("empty window: no new articles, nothing written or acked")
            return None
        if not articles:
            logger.warning("%d rows were all unreadable: acking, no digest", rows)
            self._mcp.ack_cursor(cursor)
            return None

        scored, ranking = score_groups(self._grouper.group(articles), p.tone_divisor)
        selection = select(
            scored,
            SelectParams(
                top_stories=p.top_stories,
                max_sections=p.max_sections,
                groups_per_section=p.groups_per_section,
                min_group_sources=p.min_group_sources,
                section_min_hits=p.section_min_hits,
                labels=p.labels,
            ),
        )
        listed = [*selection.top, *(g for s in selection.sections for g in s.groups)]
        summaries = {item.group.key: self._summarise(item.group) for item in listed}
        text = render_story_digest(
            now=now,
            article_count=len(articles),
            selection=selection,
            ranking=ranking,
            summaries=summaries,
            min_sources=p.min_group_sources,
            also_limit=p.also_per_group,
            body_grounded=p.summary_body_chars > 0,
        )

        path = self._sink.write(now, text)  # OSError here: no ack, window read again
        logger.info("digest written to %s\n%s", path, text)
        self._mcp.ack_cursor(cursor)
        return Digest(text, path, len(articles), cursor)

    def _read_window(self) -> tuple[list[Article], str, int]:
        """Page until a short page or the cap; returns articles, last cursor, rows."""
        p = self._params
        articles: list[Article] = []
        cursor: str | None = None
        rows = 0
        while True:
            page, cursor = self._mcp.list_new_articles(
                p.page_size, cursor, TONE_INCLUDE
            )
            rows += len(page)
            for item in page:
                try:
                    articles.append(Article.from_mcp(item))
                except ValidationError:
                    logger.warning("skipping an unreadable article row")
            if len(page) < p.page_size or rows >= p.max_articles:
                return articles, cursor, rows

    def _summarise(self, group: StoryGroup) -> str | None:
        excerpt = self._excerpt(group)
        if excerpt is None and len(group.variants) < 2:
            return None  # one headline and no stored text: a sentence adds nothing
        titles = [v.title for v in group.variants[: 1 + self._params.also_per_group]]
        try:
            return self._summariser.summarise(titles, excerpt)
        except Exception as exc:  # noqa: BLE001 - the model must never stop a digest
            logger.warning("summary for a group failed: %s", type(exc).__name__)
            return None

    def _excerpt(self, group: StoryGroup) -> str | None:
        """The stored page text of the group's best headline, clipped; None without
        one. Tries the shown headline first, then the other distinct ones. One failed
        call gives the whole group up: the platform is in trouble and headlines still
        work, while retrying every member would multiply the load."""
        cap = self._params.summary_body_chars
        if cap <= 0:
            return None
        for article in group.variants[: self._params.body_lookups_per_group]:
            try:
                full = self._mcp.get_article(article.article_id)
            except Exception as exc:  # noqa: BLE001 - bodies are optional extras
                logger.warning(
                    "get_article %s failed: %s", article.article_id, type(exc).__name__
                )
                return None
            body = full.get("body")
            if (
                full.get("body_status") == "ok"
                and isinstance(body, str)
                and body.strip()
            ):
                return _clip(body.strip(), cap)
        return None
