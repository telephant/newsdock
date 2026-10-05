"""One service layer under both MCP and REST (ADR-0003).

Cursor (AC-10): opaque base64 of "seq:<max seq seen>"; no cursor → only
articles ingested within FIRST_RUN_WINDOW (R-2). Limits clamped (design.md §3).
"""

import base64
import binascii
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from newsdock_api.domain.records import ArticleDetail, ArticleSummary, NewArticlesPage

FIRST_RUN_WINDOW = timedelta(hours=1)
MAX_PAYLOAD_BYTES = 64 * 1024
SEARCH_DEFAULT, SEARCH_MAX = 20, 100
LIST_DEFAULT, LIST_MAX = 50, 200


class NotFoundError(Exception):
    """Raised for an unknown article_id (maps to MCP error `not_found`)."""


class PayloadTooLargeError(Exception):
    """submit_analysis payload over 64 KB (design-detail §5)."""


class ArticleRepo(Protocol):
    def search(
        self,
        *,
        time_from: datetime | None,
        time_to: datetime | None,
        theme: str | None,
        domain: str | None,
        text: str | None,
        limit: int,
        before: tuple[datetime, str] | None = None,
    ) -> list[ArticleSummary]: ...

    def list_new(
        self, *, after_seq: int | None, since: datetime | None, limit: int
    ) -> list[ArticleSummary]: ...

    def upsert_analysis(
        self, article_id: str, agent_name: str, payload: dict[str, Any]
    ) -> bool: ...


def escape_like(text: str) -> str:
    """Escape ILIKE wildcards so user text is literal (TC-17)."""
    return text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def encode_cursor(seq: int) -> str:
    return base64.urlsafe_b64encode(f"seq:{seq}".encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        prefix, _, value = decoded.partition(":")
        if prefix != "seq":
            raise ValueError
        return int(value)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc


def _clamp(limit: int | None, default: int, maximum: int) -> int:
    if limit is None:
        return default
    return max(1, min(limit, maximum))


class ArticleService:
    def __init__(
        self,
        repo: ArticleRepo,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._now = now

    def search(
        self,
        *,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        theme: str | None = None,
        domain: str | None = None,
        text: str | None = None,
        limit: int | None = None,
        before: tuple[datetime, str] | None = None,
    ) -> list[ArticleSummary]:
        return self._repo.search(
            time_from=time_from,
            time_to=time_to,
            theme=theme,
            domain=domain,
            text=text,
            limit=_clamp(limit, SEARCH_DEFAULT, SEARCH_MAX),
            before=before,
        )

    def list_new(self, *, cursor: str | None, limit: int | None) -> NewArticlesPage:
        after_seq = decode_cursor(cursor) if cursor else None
        since = None if cursor else self._now() - FIRST_RUN_WINDOW
        articles = self._repo.list_new(
            after_seq=after_seq,
            since=since,
            limit=_clamp(limit, LIST_DEFAULT, LIST_MAX),
        )
        if articles:
            next_cursor = encode_cursor(max(a.seq for a in articles))
        else:  # same cursor back: nothing new (AC-10)
            next_cursor = cursor if cursor else encode_cursor(0)
        return NewArticlesPage(articles=articles, next_cursor=next_cursor)

    def submit_analysis(
        self, article_id: str, agent_name: str, payload: dict[str, Any]
    ) -> None:
        if len(json.dumps(payload).encode()) > MAX_PAYLOAD_BYTES:
            raise PayloadTooLargeError("payload over 64 KB")
        if not self._repo.upsert_analysis(article_id, agent_name, payload):
            raise NotFoundError(article_id)


class DetailRepo(Protocol):  # implemented by the same adapter class
    def get(self, article_id: str) -> ArticleDetail | None: ...


def get_article(repo: DetailRepo, article_id: str) -> ArticleDetail:
    detail = repo.get(article_id)
    if detail is None:
        raise NotFoundError(article_id)
    return detail
