"""TC-17, TC-18, TC-20, TC-22, TC-23, TC-24 (service side) over a fake repo."""

from datetime import UTC, datetime, timedelta

import pytest
from newsdock_api.domain.records import ArticleSummary
from newsdock_api.domain.service import (
    ArticleService,
    NotFoundError,
    PayloadTooLargeError,
    ServiceLimits,
    decode_cursor,
    encode_cursor,
    escape_like,
)

NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)
LIMITS = ServiceLimits(
    search_default=20,
    search_max=100,
    list_new_default=50,
    list_new_max=200,
    max_payload_bytes=64 * 1024,
    first_run_window=timedelta(hours=1),
)


def summary(seq: int) -> ArticleSummary:
    return ArticleSummary(
        article_id=f"hash{seq}", title=f"t{seq}", url=f"https://e.com/{seq}",
        domain="e.com", published_at=NOW, themes=["ECON_X"], seq=seq,
    )  # fmt: skip


class FakeRepo:
    def __init__(self) -> None:
        self.search_limits: list[int] = []
        self.list_calls: list[tuple[int | None, datetime | None, int]] = []
        self.upserts: list[tuple[str, str]] = []
        self.articles_exist = True
        self.new: list[ArticleSummary] = []

    def search(self, *, limit: int, **kwargs: object) -> list[ArticleSummary]:
        self.search_limits.append(limit)
        return []

    def list_new(
        self, *, after_seq: int | None, since: datetime | None, limit: int
    ) -> list[ArticleSummary]:
        self.list_calls.append((after_seq, since, limit))
        return self.new

    def upsert_analysis(
        self, article_id: str, agent_name: str, payload: dict[str, object]
    ) -> bool:
        self.upserts.append((article_id, agent_name))
        return self.articles_exist


def service(
    repo: FakeRepo | None = None, limits: ServiceLimits = LIMITS
) -> tuple[ArticleService, FakeRepo]:
    repo = repo or FakeRepo()
    return ArticleService(repo, limits=limits, now=lambda: NOW), repo


# TC-17: ILIKE wildcards in the text filter are escaped
def test_escape_like_neutralizes_wildcards() -> None:
    assert escape_like("100%_done") == r"100\%\_done"
    assert escape_like(r"a\b") == r"a\\b"


# TC-18: limits clamped — search default 20 / max 100; list default 50 / max 200
def test_search_limit_clamped() -> None:
    svc, repo = service()
    svc.search(limit=None)
    svc.search(limit=999)
    svc.search(limit=0)
    assert repo.search_limits == [20, 100, 1]


def test_list_new_limit_clamped() -> None:
    svc, repo = service()
    svc.list_new(cursor=None, limit=None)
    svc.list_new(cursor=None, limit=999)
    assert [c[2] for c in repo.list_calls] == [50, 200]


# TC-20: no cursor → only articles ingested within the last hour
def test_first_run_window_is_one_hour() -> None:
    svc, repo = service()
    svc.list_new(cursor=None, limit=10)
    (after_seq, since, _) = repo.list_calls[0]
    assert after_seq is None and since == NOW - timedelta(hours=1)


def test_cursor_roundtrip_and_same_cursor_back_when_empty() -> None:
    assert decode_cursor(encode_cursor(42)) == 42
    svc, repo = service()
    repo.new = [summary(7), summary(9)]
    page = svc.list_new(cursor=None, limit=10)
    assert decode_cursor(page.next_cursor) == 9
    repo.new = []
    page2 = svc.list_new(cursor=page.next_cursor, limit=10)
    assert page2.articles == [] and page2.next_cursor == page.next_cursor


def test_invalid_cursor_is_an_error() -> None:
    svc, _ = service()
    with pytest.raises(ValueError, match="invalid_cursor"):
        svc.list_new(cursor="garbage!!", limit=10)


# TC-22: unknown article → not_found
def test_submit_unknown_article_raises_not_found() -> None:
    svc, repo = service()
    repo.articles_exist = False
    with pytest.raises(NotFoundError):
        svc.submit_analysis("nope", "demo", {"score": 0.5})


# TC-23: payload > 64 KB rejected
def test_oversized_payload_rejected() -> None:
    svc, _ = service()
    with pytest.raises(PayloadTooLargeError):
        svc.submit_analysis("h", "demo", {"blob": "x" * 65 * 1024})


# TC-24 (service side): resubmission goes through the upsert (replace, latest wins)
def test_resubmission_upserts() -> None:
    svc, repo = service()
    svc.submit_analysis("h", "demo", {"score": 0.1})
    svc.submit_analysis("h", "demo", {"score": 0.9})
    assert repo.upserts == [("h", "demo"), ("h", "demo")]


# TC-16: limits and windows come from the injected ServiceLimits, not constants
CUSTOM = ServiceLimits(
    search_default=5,
    search_max=7,
    list_new_default=6,
    list_new_max=8,
    max_payload_bytes=100,
    first_run_window=timedelta(minutes=10),
)


def test_tc16_custom_search_and_list_limits() -> None:
    svc, repo = service(limits=CUSTOM)
    svc.search(limit=None)
    svc.search(limit=999)
    svc.list_new(cursor=None, limit=None)
    svc.list_new(cursor=None, limit=999)
    assert repo.search_limits == [5, 7]
    assert [c[2] for c in repo.list_calls] == [6, 8]


def test_tc16_custom_first_run_window() -> None:
    svc, repo = service(limits=CUSTOM)
    svc.list_new(cursor=None, limit=10)
    assert repo.list_calls[0][1] == NOW - timedelta(minutes=10)


def test_tc16_custom_payload_cap_and_message() -> None:
    svc, _ = service(limits=CUSTOM)
    svc.submit_analysis("h", "agent", {"k": "x" * 10})
    with pytest.raises(PayloadTooLargeError, match="100"):
        svc.submit_analysis("h", "agent", {"k": "x" * 200})
