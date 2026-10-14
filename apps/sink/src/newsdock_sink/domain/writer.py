"""Sink batch logic (M2a design-detail §2): story grouping, poison fallback.

Each copy becomes an `article_sources` row; the first copy of a story (same
`story_key` within the published_at window, ADR-0012) also becomes the
canonical `articles` row. A copy never joins a story that already holds a
different page of the same domain (ADR-0012 amendment 2026-10-09, AC-13).
A transient DB outage raises DbUnavailable so the
caller backs off WITHOUT committing offsets; a row Postgres rejects goes to
gkg.dlq as `bad_field` and the batch still commits (M1 R-1, preserved).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from newsdock_core.contracts import CleanArticle, DlqMessage, DlqReason
from newsdock_core.stories import can_join, story_key
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class DbUnavailable(Exception):
    """Connection-level failure: retry the whole batch later, do not commit."""


class RowRejected(Exception):
    """Postgres rejected data in a row (NUL byte, out-of-range value, …)."""


@dataclass(frozen=True)
class SinkItem:
    key: str  # url_hash (gkg.clean key)
    value: bytes  # CleanArticle JSON


@dataclass(frozen=True)
class BatchResult:
    """AC-12: canonicals + grouped + url_duplicates + dlq == batch size."""

    canonicals: int  # new stories (articles rows inserted)
    grouped: int  # copies attached to an existing canonical
    url_duplicates: int  # already-stored URLs (redelivery, re-listed slots)
    dlq: int


@dataclass
class Candidate:
    """A stored story a copy might join: its canonical id, time and members."""

    canonical_id: str
    published_at: datetime
    sources: list[tuple[str | None, str]]  # (domain, url) of every stored copy


class StoryWriter(Protocol):
    def find_candidates(
        self, story_key: str, published_at: datetime, window: timedelta
    ) -> list[Candidate]:
        """Canonicals with this key within the window, oldest first, with sources."""
        ...

    def insert_canonical(self, article: CleanArticle, story_key: str) -> bool: ...

    def insert_source(self, article: CleanArticle, canonical_id: str) -> bool: ...


class DlqSink(Protocol):
    def send(self, key: str, message: DlqMessage) -> None: ...


def _dlq_message(item: SinkItem) -> DlqMessage:
    slot = ""
    try:
        parsed = CleanArticle.model_validate_json(item.value)
        slot = parsed.slot
    except ValidationError:
        pass
    return DlqMessage(
        reason=DlqReason.bad_field,
        slot=slot or "unknown",
        row_no=-1,
        line=item.value.decode("utf-8", errors="replace"),
    )


def process_batch(
    items: list[SinkItem],
    writer: StoryWriter,
    dlq: DlqSink,
    *,
    window: timedelta,
) -> BatchResult:
    """Write one batch. Raises DbUnavailable; never raises on bad rows."""
    canonicals = grouped = url_duplicates = dlq_count = 0
    # in-batch cache so copies arriving together need one DB lookup (TC-14)
    cache: dict[str, list[Candidate]] = {}

    def pick(key: str, article: CleanArticle) -> Candidate | None:
        for candidate in cache.get(key, []):
            in_window = abs(article.published_at - candidate.published_at) <= window
            if in_window and can_join(article.domain, article.url, candidate.sources):
                return candidate
        return None

    def choose(key: str, article: CleanArticle) -> Candidate | None:
        found = pick(key, article)
        if found is not None:
            return found
        known = cache.setdefault(key, [])
        for candidate in writer.find_candidates(key, article.published_at, window):
            if all(candidate.canonical_id != c.canonical_id for c in known):
                known.append(candidate)
        known.sort(key=lambda c: c.published_at)
        return pick(key, article)

    for sink_item in items:
        try:
            article = CleanArticle.model_validate_json(sink_item.value)
        except ValidationError:
            dlq.send(sink_item.key, _dlq_message(sink_item))
            dlq_count += 1
            continue
        key = story_key(article.title)
        try:
            canonical = choose(key, article)
            if canonical is None:
                if writer.insert_canonical(article, key):
                    canonicals += 1
                else:
                    # URL already stored (pre-feature row or redelivery edge):
                    # treat the existing row as this story's canonical
                    url_duplicates += 1
                canonical = Candidate(article.url_hash, article.published_at, [])
                cache.setdefault(key, []).append(canonical)
                writer.insert_source(article, canonical.canonical_id)  # own source
            else:
                source_is_new = writer.insert_source(article, canonical.canonical_id)
                if source_is_new and canonical.canonical_id != article.url_hash:
                    grouped += 1
                else:  # redelivered copy, or healing the canonical's own source
                    url_duplicates += 1
        except RowRejected as exc:
            logger.warning("row %s rejected: %s", article.url_hash, exc)
            dlq.send(
                article.url_hash,
                DlqMessage(
                    reason=DlqReason.bad_field,
                    slot=article.slot,
                    row_no=-1,
                    line=article.model_dump_json(),
                ),
            )
            dlq_count += 1
            continue
        if (article.domain, article.url) not in canonical.sources:
            canonical.sources.append((article.domain, article.url))

    result = BatchResult(
        canonicals=canonicals,
        grouped=grouped,
        url_duplicates=url_duplicates,
        dlq=dlq_count,
    )
    logger.info(  # AC-12: observable dedup ratio per batch
        "dedup: %d canonicals, %d grouped copies, %d url-duplicates, %d dlq",
        result.canonicals,
        result.grouped,
        result.url_duplicates,
        result.dlq,
    )
    return result
