"""Shared fixtures for the what-happen digest tests (grown task by task).

Tests use `--import-mode=importlib`, so helpers are fixtures, not imported modules.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from newsdock_agent.domain.articles import Article


@pytest.fixture
def make_article() -> Callable[..., Article]:
    def make(
        n: int = 1,
        *,
        themes: list[str] | None = None,
        source_count: int = 1,
        published_at: datetime | None = None,
        title: str | None = None,
        url: str | None = None,
        domain: str | None = "example.com",
    ) -> Article:
        return Article(
            article_id=f"id{n}",
            title=title if title is not None else f"Headline {n}",
            url=url if url is not None else f"https://example.com/{n}",
            domain=domain,
            published_at=published_at or datetime(2026, 10, 30, 14, 0, tzinfo=UTC),
            themes=themes or [],
            source_count=source_count,
        )

    return make


class FakeClock:
    """An injectable clock: `sleep` advances `now` instead of waiting."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 10, 30, 14, 7, tzinfo=UTC)
        self.sleeps: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
