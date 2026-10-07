"""TC-13, TC-14 (M2a) + M1 semantics: poison→dlq, db-down→no commit, counts sum."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from newsdock_core.contracts import CleanArticle, DlqMessage, DlqReason
from newsdock_sink.domain.writer import (
    DEFAULT_WINDOW,
    DbUnavailable,
    RowRejected,
    SinkItem,
    process_batch,
)

ROOT = Path(__file__).resolve().parents[4]
EXPECTED = ROOT / "packages" / "core" / "tests" / "fixtures" / "expected_articles.json"
NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)


def fixture_articles(n: int = 5) -> list[CleanArticle]:
    with EXPECTED.open() as f:
        return [CleanArticle.model_validate(a) for a in json.load(f)][:n]


def item(article: CleanArticle) -> SinkItem:
    return SinkItem(key=article.url_hash, value=article.model_dump_json().encode())


def copy_of(
    article: CleanArticle, *, url: str, title: str | None = None, hours: float = 0.0
) -> CleanArticle:
    import hashlib

    return article.model_copy(
        update={
            "url": url,
            "url_hash": hashlib.sha256(url.encode()).hexdigest(),
            "title": title if title is not None else article.title,
            "published_at": article.published_at + timedelta(hours=hours),
        }
    )


class FakeStoryWriter:
    def __init__(
        self, poison: frozenset[str] = frozenset(), down: bool = False
    ) -> None:
        self.poison, self.down = poison, down
        self.canonicals: dict[str, tuple[str, datetime]] = {}  # url_hash -> (key, pub)
        self.sources: dict[str, str] = {}  # source url_hash -> canonical id
        self.find_calls = 0

    def _guard(self, url_hash: str) -> None:
        if self.down:
            raise DbUnavailable("connection refused")
        if url_hash in self.poison:
            raise RowRejected("invalid byte sequence")

    def find_canonical(
        self, story_key: str, published_at: datetime, window: timedelta
    ) -> tuple[str, datetime] | None:
        if self.down:
            raise DbUnavailable("connection refused")
        self.find_calls += 1
        for cid, (key, pub) in self.canonicals.items():
            if key == story_key and abs(published_at - pub) <= window:
                return cid, pub
        return None

    def insert_canonical(self, article: CleanArticle, story_key: str) -> bool:
        self._guard(article.url_hash)
        if article.url_hash in self.canonicals:
            return False
        self.canonicals[article.url_hash] = (story_key, article.published_at)
        return True

    def insert_source(self, article: CleanArticle, canonical_id: str) -> bool:
        self._guard(article.url_hash)
        if article.url_hash in self.sources:
            return False
        self.sources[article.url_hash] = canonical_id
        return True


class FakeDlq:
    def __init__(self) -> None:
        self.sent: list[tuple[str, DlqMessage]] = []

    def send(self, key: str, message: DlqMessage) -> None:
        self.sent.append((key, message))


# ---- TC-14: both copies in one batch → one canonical via the in-batch cache --


def test_in_batch_cache_yields_one_canonical() -> None:
    base = fixture_articles(1)[0]
    copy = copy_of(base, url="https://other-site.example/same-story", hours=1)
    writer, dlq = FakeStoryWriter(), FakeDlq()
    result = process_batch([item(base), item(copy)], writer, dlq)
    assert (result.canonicals, result.grouped, result.url_duplicates) == (1, 1, 0)
    assert len(writer.canonicals) == 1 and len(writer.sources) == 2
    assert writer.find_calls == 1  # second copy came from the cache, not the DB
    assert writer.sources[copy.url_hash] == base.url_hash


# ---- TC-13: the counters always sum to the batch --------------------------


def test_counts_sum_to_batch_across_all_paths() -> None:
    base = fixture_articles(2)
    story, other = base[0], base[1]
    copy = copy_of(story, url="https://copy.example/x", hours=2)
    redelivered = story  # same url again
    bad = SinkItem(key="k", value=b"{not json")
    writer, dlq = FakeStoryWriter(), FakeDlq()
    items = [item(story), item(copy), item(other), item(redelivered), bad]
    result = process_batch(items, writer, dlq)
    assert (result.canonicals, result.grouped) == (2, 1)
    assert (result.url_duplicates, result.dlq) == (1, 1)
    assert result.canonicals + result.grouped + result.url_duplicates + result.dlq == 5


def test_window_guard_splits_same_key() -> None:  # AC-5 logic at unit level
    story = fixture_articles(1)[0]
    far = copy_of(story, url="https://late.example/x", hours=72)  # > 48 h window
    writer, dlq = FakeStoryWriter(), FakeDlq()
    result = process_batch([item(story), item(far)], writer, dlq)
    assert result.canonicals == 2 and result.grouped == 0
    assert DEFAULT_WINDOW == timedelta(hours=48)


# ---- M1 semantics preserved -------------------------------------------------


def test_poison_row_goes_to_dlq_and_the_rest_are_written() -> None:
    articles = fixture_articles(5)
    poison_key = articles[2].url_hash
    writer = FakeStoryWriter(poison=frozenset({poison_key}))
    dlq = FakeDlq()
    result = process_batch([item(a) for a in articles], writer, dlq)
    assert result.canonicals == 4 and result.dlq == 1
    (key, message) = dlq.sent[0]
    assert key == poison_key and message.reason == DlqReason.bad_field
    assert poison_key not in writer.canonicals


def test_db_down_raises_so_offsets_are_not_committed() -> None:
    writer, dlq = FakeStoryWriter(down=True), FakeDlq()
    with pytest.raises(DbUnavailable):
        process_batch([item(a) for a in fixture_articles(3)], writer, dlq)
    assert dlq.sent == []


def test_unparseable_clean_message_goes_to_dlq() -> None:
    writer, dlq = FakeStoryWriter(), FakeDlq()
    bad = SinkItem(key="k", value=b"{not json")
    result = process_batch([bad, *(item(a) for a in fixture_articles(2))], writer, dlq)
    assert result.canonicals == 2 and result.dlq == 1
    assert dlq.sent[0][1].reason == DlqReason.bad_field
