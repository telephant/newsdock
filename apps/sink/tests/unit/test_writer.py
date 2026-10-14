"""TC-13, TC-14 (M2a) + M1 semantics: poison→dlq, db-down→no commit, counts sum."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from newsdock_core.contracts import CleanArticle, DlqMessage, DlqReason
from newsdock_sink.domain.writer import (
    Candidate,
    DbUnavailable,
    RowRejected,
    SinkItem,
    process_batch,
)

ROOT = Path(__file__).resolve().parents[4]
EXPECTED = ROOT / "packages" / "core" / "tests" / "fixtures" / "expected_articles.json"
NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)

WINDOW = timedelta(hours=48)


def fixture_articles(n: int = 5) -> list[CleanArticle]:
    with EXPECTED.open() as f:
        return [CleanArticle.model_validate(a) for a in json.load(f)][:n]


def item(article: CleanArticle) -> SinkItem:
    return SinkItem(key=article.url_hash, value=article.model_dump_json().encode())


def copy_of(
    article: CleanArticle, *, url: str, title: str | None = None, hours: float = 0.0
) -> CleanArticle:
    import hashlib
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    return article.model_copy(
        update={
            "url": url,
            "domain": ".".join(host.split(".")[-2:]),
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
        self.source_info: dict[
            str, tuple[str | None, str]
        ] = {}  # hash -> (domain, url)
        self.find_calls = 0

    def _guard(self, url_hash: str) -> None:
        if self.down:
            raise DbUnavailable("connection refused")
        if url_hash in self.poison:
            raise RowRejected("invalid byte sequence")

    def find_candidates(
        self, story_key: str, published_at: datetime, window: timedelta
    ) -> list[Candidate]:
        if self.down:
            raise DbUnavailable("connection refused")
        self.find_calls += 1
        found: list[Candidate] = []
        for cid, (key, pub) in sorted(self.canonicals.items(), key=lambda i: i[1][1]):
            if key == story_key and abs(published_at - pub) <= window:
                members = [
                    self.source_info[h] for h, c in self.sources.items() if c == cid
                ]
                found.append(Candidate(cid, pub, members))
        return found

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
        self.source_info[article.url_hash] = (article.domain, article.url)
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
    result = process_batch([item(base), item(copy)], writer, dlq, window=WINDOW)
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
    result = process_batch(items, writer, dlq, window=WINDOW)
    assert (result.canonicals, result.grouped) == (2, 1)
    assert (result.url_duplicates, result.dlq) == (1, 1)
    assert result.canonicals + result.grouped + result.url_duplicates + result.dlq == 5


def test_window_guard_splits_same_key() -> None:  # AC-5 logic at unit level
    story = fixture_articles(1)[0]
    far = copy_of(story, url="https://late.example/x", hours=72)  # > 48 h window
    writer, dlq = FakeStoryWriter(), FakeDlq()
    result = process_batch([item(story), item(far)], writer, dlq, window=WINDOW)
    assert result.canonicals == 2 and result.grouped == 0


# ---- M1 semantics preserved -------------------------------------------------


def test_poison_row_goes_to_dlq_and_the_rest_are_written() -> None:
    articles = fixture_articles(5)
    poison_key = articles[2].url_hash
    writer = FakeStoryWriter(poison=frozenset({poison_key}))
    dlq = FakeDlq()
    result = process_batch([item(a) for a in articles], writer, dlq, window=WINDOW)
    assert result.canonicals == 4 and result.dlq == 1
    (key, message) = dlq.sent[0]
    assert key == poison_key and message.reason == DlqReason.bad_field
    assert poison_key not in writer.canonicals


def test_db_down_raises_so_offsets_are_not_committed() -> None:
    writer, dlq = FakeStoryWriter(down=True), FakeDlq()
    with pytest.raises(DbUnavailable):
        process_batch(
            [item(a) for a in fixture_articles(3)], writer, dlq, window=WINDOW
        )
    assert dlq.sent == []


def test_unparseable_clean_message_goes_to_dlq() -> None:
    writer, dlq = FakeStoryWriter(), FakeDlq()
    bad = SinkItem(key="k", value=b"{not json")
    result = process_batch(
        [bad, *(item(a) for a in fixture_articles(2))], writer, dlq, window=WINDOW
    )
    assert result.canonicals == 2 and result.dlq == 1
    assert dlq.sent[0][1].reason == DlqReason.bad_field


# ---- AC-13 / TC-15: same-domain look-alike pages must not group ---------------


def story_pair(
    url_a: str, url_b: str, hours: float = 1
) -> tuple[CleanArticle, CleanArticle]:
    base = copy_of(fixture_articles(1)[0], url=url_a, title="The Miami Student")
    return base, copy_of(base, url=url_b, hours=hours)


def test_tc15_same_domain_different_pages_stay_separate_stories() -> None:
    a, b = story_pair(
        "https://www.miamistudent.net/staff/ada-lillie-worthington",
        "https://www.miamistudent.net/staff/alyssa-vasquez",
    )
    writer, dlq = FakeStoryWriter(), FakeDlq()
    result = process_batch([item(a), item(b)], writer, dlq, window=WINDOW)
    assert (result.canonicals, result.grouped) == (2, 0)
    assert len(writer.canonicals) == 2


def test_tc15_same_domain_same_page_other_host_still_groups() -> None:
    a, b = story_pair(
        "https://wtak.iheart.com/content/2026-10-08-aerosmith",
        "https://937theriver.iheart.com/content/2026-10-08-aerosmith",
    )
    writer, dlq = FakeStoryWriter(), FakeDlq()
    result = process_batch([item(a), item(b)], writer, dlq, window=WINDOW)
    assert (result.canonicals, result.grouped) == (1, 1)


def test_tc15_other_domain_copy_joins_the_first_compatible_story() -> None:
    a, b = story_pair(
        "https://www.miamistudent.net/staff/ada",
        "https://www.miamistudent.net/staff/alyssa",
    )
    c = copy_of(a, url="https://elsewhere.org/miami-student", hours=2)
    writer, dlq = FakeStoryWriter(), FakeDlq()
    process_batch([item(a), item(b), item(c)], writer, dlq, window=WINDOW)
    assert writer.sources[c.url_hash] == a.url_hash  # oldest compatible story


def test_tc15_redelivery_of_the_second_story_stays_idempotent() -> None:
    a, b = story_pair(
        "https://www.miamistudent.net/staff/ada",
        "https://www.miamistudent.net/staff/alyssa",
    )
    writer, dlq = FakeStoryWriter(), FakeDlq()
    process_batch([item(a), item(b)], writer, dlq, window=WINDOW)
    again = process_batch([item(b)], writer, dlq, window=WINDOW)  # cold cache
    assert (again.canonicals, again.grouped, again.url_duplicates) == (0, 0, 1)
    assert len(writer.canonicals) == 2 and len(writer.sources) == 2
