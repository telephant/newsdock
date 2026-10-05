"""Sink batch logic (design-detail §2): upsert, poison fallback, dedup count.

A transient DB outage raises DbUnavailable so the caller backs off WITHOUT
committing offsets; a row Postgres rejects goes to gkg.dlq as `bad_field` and
the batch still commits (R-1).
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from newsdock_core.contracts import CleanArticle, DlqMessage, DlqReason
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
    written: int
    conflicts: int  # duplicates absorbed by ON CONFLICT (R-12 measurement)
    dlq: int


class ArticleWriter(Protocol):
    def insert_batch(self, articles: list[CleanArticle]) -> int: ...

    def insert_one(self, article: CleanArticle) -> int: ...


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
    items: list[SinkItem], writer: ArticleWriter, dlq: DlqSink
) -> BatchResult:
    """Write one batch. Raises DbUnavailable; never raises on bad rows."""
    articles: list[CleanArticle] = []
    dlq_count = 0
    for item in items:
        try:
            articles.append(CleanArticle.model_validate_json(item.value))
        except ValidationError:
            dlq.send(item.key, _dlq_message(item))
            dlq_count += 1

    written = 0
    rejected = 0
    try:
        written = writer.insert_batch(articles)
    except RowRejected:
        for article in articles:  # row-by-row fallback (R-1)
            try:
                written += writer.insert_one(article)
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
                rejected += 1
    conflicts = len(articles) - written - rejected  # absorbed duplicates
    result = BatchResult(
        written=written, conflicts=max(conflicts, 0), dlq=dlq_count + rejected
    )
    if result.conflicts:
        logger.info("dedup: %d duplicates absorbed", result.conflicts)
    return result
