"""Sink batch logic (M2a design-detail §2): story grouping, poison fallback.

Each copy becomes an `article_sources` row; the first copy of a story (same
`story_key` within the published_at window, ADR-0012) also becomes the
canonical `articles` row. A transient DB outage raises DbUnavailable so the
caller backs off WITHOUT committing offsets; a row Postgres rejects goes to
gkg.dlq as `bad_field` and the batch still commits (M1 R-1, preserved).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from newsdock_core.contracts import CleanArticle, DlqMessage, DlqReason
from newsdock_core.stories import story_key
from pydantic import ValidationError

logger = logging.getLogger(__name__)

DEFAULT_WINDOW = timedelta(hours=48)  # NEWSDOCK_STORY_WINDOW_HOURS (D-5)


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


class StoryWriter(Protocol):
    def find_canonical(
        self, story_key: str, published_at: datetime, window: timedelta
    ) -> tuple[str, datetime] | None: ...

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
    window: timedelta = DEFAULT_WINDOW,
) -> BatchResult:
    """Write one batch. Raises DbUnavailable; never raises on bad rows."""
    canonicals = grouped = url_duplicates = dlq_count = 0
    # in-batch cache so copies arriving together need one DB lookup (TC-14)
    cache: dict[str, list[tuple[str, datetime]]] = {}

    def cached(key: str, published_at: datetime) -> tuple[str, datetime] | None:
        for cid, pub in cache.get(key, []):
            if abs(published_at - pub) <= window:
                return cid, pub
        return None

    for sink_item in items:
        try:
            article = CleanArticle.model_validate_json(sink_item.value)
        except ValidationError:
            dlq.send(sink_item.key, _dlq_message(sink_item))
            dlq_count += 1
            continue
        key = story_key(article.title)
        try:
            canonical = cached(key, article.published_at) or writer.find_canonical(
                key, article.published_at, window
            )
            if canonical is None:
                if writer.insert_canonical(article, key):
                    canonicals += 1
                else:
                    # URL already stored (pre-feature row or redelivery edge):
                    # treat the existing row as this story's canonical
                    url_duplicates += 1
                canonical = (article.url_hash, article.published_at)
                writer.insert_source(article, canonical[0])  # own source row
            else:
                source_is_new = writer.insert_source(article, canonical[0])
                if source_is_new and canonical[0] != article.url_hash:
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
        entries = cache.setdefault(key, [])
        if canonical not in entries:
            entries.append(canonical)

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
