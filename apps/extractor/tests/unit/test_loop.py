"""TC-2, TC-5, TC-12 at the worker level (fakes, no database, no network).

The worker takes due rows newest first, one per site, fetches them, extracts the text
and stores one outcome per row: `ok` with passages, a final status, a retry, or a wait.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from newsdock_extractor.domain.loop import (
    DbUnavailable,
    ExtractWorker,
    WorkerConfig,
    decode_body,
)
from newsdock_extractor.domain.picking import QueueRow
from newsdock_extractor.domain.results import (
    FailureKind,
    Fetched,
    FetchFailure,
)
from newsdock_extractor.domain.schedule import HostScheduler
from newsdock_extractor.domain.status import BodyStatus

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
NEWS = (FIXTURES / "news_page.html").read_bytes()
STUB = (FIXTURES / "stub_page.html").read_bytes()
NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.seconds = 1_000.0

    def __call__(self) -> float:
        return self.seconds


def row(seq: int, host: str = "a.example", attempts: int = 0) -> QueueRow:
    return QueueRow(
        url_hash=f"h{seq}",
        url=f"https://{host}/story-{seq}",
        seq=seq,
        created_at=NOW - timedelta(hours=1),
        next_attempt_at=NOW - timedelta(minutes=1),
        attempts=attempts,
    )


class FakeRepo:
    def __init__(self, rows: list[QueueRow]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, Any]] = []
        self.race = False  # store_ok answers False: another worker was first
        self.fail_discover: Exception | None = None
        self.fail_store: Exception | None = None

    def discover(self, *, now: datetime, backfill_hours: int) -> int:
        if self.fail_discover:
            raise self.fail_discover
        self.calls.append(("discover", (now, backfill_hours)))
        return 0

    def next_batch(
        self, *, now: datetime, retention_days: int, limit: int
    ) -> list[QueueRow]:
        self.calls.append(("next_batch", (now, retention_days, limit)))
        return list(self.rows)

    def _store(self, name: str, payload: dict[str, Any]) -> bool:
        if self.fail_store:
            raise self.fail_store
        self.calls.append((name, payload))
        # a stored row leaves the due queue (done, or waiting for a later attempt)
        self.rows = [r for r in self.rows if r.url_hash != payload["url_hash"]]
        return not self.race

    def store_ok(self, url_hash: str, **kw: Any) -> bool:
        return self._store("ok", {"url_hash": url_hash, **kw})

    def store_final(self, url_hash: str, **kw: Any) -> bool:
        return self._store("final", {"url_hash": url_hash, **kw})

    def store_retry(self, url_hash: str, **kw: Any) -> bool:
        return self._store("retry", {"url_hash": url_hash, **kw})

    def defer(self, url_hash: str, **kw: Any) -> bool:
        return self._store("defer", {"url_hash": url_hash, **kw})

    def stored(self, kind: str) -> list[dict[str, Any]]:
        return [p for name, p in self.calls if name == kind]


class FakeFetcher:
    def __init__(self, results: dict[str, Any] | None = None) -> None:
        self.results = results or {}
        self.urls: list[str] = []

    async def fetch(self, url: str) -> Fetched | FetchFailure:
        self.urls.append(url)
        outcome = self.results.get(url)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, Fetched | FetchFailure), (
            f"no result scripted for {url}"
        )
        return outcome


def page(url: str, body: bytes = NEWS, crawl_delay: float | None = None) -> Fetched:
    return Fetched(
        body=body,
        final_url=url,
        http_status=200,
        wire_bytes=len(body) // 4,
        charset="utf-8",
        crawl_delay=crawl_delay,
    )


def failure(kind: FailureKind, status: BodyStatus, **kw: Any) -> FetchFailure:
    return FetchFailure(kind=kind, status=status, reason="test", **kw)


def make(
    rows: list[QueueRow],
    results: dict[str, Any] | None = None,
    **config: Any,
) -> tuple[ExtractWorker, FakeRepo, FakeFetcher, HostScheduler[QueueRow], Clock]:
    clock = Clock()
    scheduler: HostScheduler[QueueRow] = HostScheduler(
        clock=clock, per_host_delay=5.0, max_crawl_delay=30.0
    )
    base: dict[str, Any] = {
        "batch_size": 200,
        "concurrency": 16,
        "retention_days": 7,
        "backfill_hours": 6,
        "min_chars": 200,
        "text_cap_chars": 20_000,
        "passage_chars": 1000,
        "passage_max_chars": 1200,
        "max_attempts": 3,
        "retry_backoff_minutes": (5, 30),
        "max_crawl_delay_seconds": 30.0,
        "robots_failure_minutes": 60,
    }
    base.update(config)
    repo, fetcher = FakeRepo(rows), FakeFetcher(results)
    worker = ExtractWorker(
        repo, fetcher, scheduler, WorkerConfig(**base), clock=lambda: NOW
    )
    return worker, repo, fetcher, scheduler, clock


def run_pass(worker: ExtractWorker) -> Any:
    return asyncio.run(worker.run_pass())


# ---------------------------------------------------------------- the happy path
def test_a_page_becomes_text_and_passages_in_one_store_call() -> None:
    first = row(1)
    worker, repo, fetcher, _, _ = make([first], {first.url: page(first.url)})
    result = run_pass(worker)
    assert result.processed == 1
    (ok,) = repo.stored("ok")
    assert ok["url_hash"] == "h1" and ok["http_status"] == 200
    assert "Governor Alex Sample" in ok["text"] and "SITE-NAV-MARKER" not in ok["text"]
    assert ok["passages"] and all(0 < len(p) <= 1200 for p in ok["passages"])
    assert ok["attempts"] == 1 and ok["fetched_at"] == NOW
    assert repo.stored("final") == repo.stored("retry") == repo.stored("defer") == []


def test_each_pass_discovers_first_and_reads_the_queue_with_the_settings() -> None:
    worker, repo, _, _, _ = make([])
    result = run_pass(worker)
    assert result.processed == 0
    assert [name for name, _ in repo.calls] == ["discover", "next_batch"]
    assert repo.calls[0][1] == (NOW, 6)
    assert repo.calls[1][1] == (NOW, 7, 200)


def test_a_stub_page_ends_as_no_text_without_passages() -> None:
    first = row(1)
    worker, repo, _, _, _ = make([first], {first.url: page(first.url, STUB)})
    run_pass(worker)
    (final,) = repo.stored("final")
    assert final["status"] is BodyStatus.no_text and final["http_status"] == 200
    assert repo.stored("ok") == []


def test_the_charset_of_the_response_is_used_to_decode() -> None:
    assert decode_body("café".encode("latin-1"), "iso-8859-1") == "café"
    assert decode_body("café".encode(), None) == "café"
    assert decode_body(b"caf\xe9", "utf-8") == "caf�"  # replacement, never an error
    assert decode_body(b"abc", "no-such-charset") == "abc"


# ---------------------------------------------------------------- final failures
@pytest.mark.parametrize(
    ("status", "http_status"),
    [
        (BodyStatus.blocked_robots, None),
        (BodyStatus.blocked_address, None),
        (BodyStatus.http_error, 403),
        (BodyStatus.http_error, 451),
        (BodyStatus.not_html, 200),
        (BodyStatus.too_large, 200),
    ],
)
def test_final_failures_are_stored_with_their_status(
    status: BodyStatus, http_status: int | None
) -> None:
    first = row(1)
    outcome = failure(FailureKind.final, status, http_status=http_status)
    worker, repo, _, _, _ = make([first], {first.url: outcome})
    run_pass(worker)
    (final,) = repo.stored("final")
    assert (final["status"], final["http_status"]) == (status, http_status)
    assert final["attempts"] == 1
    assert repo.stored("retry") == [] and repo.stored("ok") == []


# ---------------------------------------------------------------- retries (TC-12)
def test_a_transient_failure_is_retried_later_and_the_third_one_is_final() -> None:
    cases = [
        (0, BodyStatus.pending, 5),
        (1, BodyStatus.pending, 30),
        (2, BodyStatus.failed, None),
    ]
    for attempts, status, minutes in cases:
        first = row(1, attempts=attempts)
        outcome = failure(FailureKind.transient, BodyStatus.failed, http_status=500)
        worker, repo, _, _, _ = make([first], {first.url: outcome})
        run_pass(worker)
        (retry,) = repo.stored("retry")
        assert retry["status"] is status and retry["attempts"] == attempts + 1
        assert retry["http_status"] == 500
        expected = None if minutes is None else NOW + timedelta(minutes=minutes)
        assert retry["next_attempt_at"] == expected


def test_a_429_with_retry_after_raises_the_delay_of_that_site() -> None:
    first, second = row(1), row(2)
    outcome = failure(
        FailureKind.transient,
        BodyStatus.failed,
        http_status=429,
        retry_after_seconds=12,
    )
    worker, repo, _, scheduler, clock = make([first], {first.url: outcome})
    run_pass(worker)
    (retry,) = repo.stored("retry")
    assert retry["next_attempt_at"] == NOW + timedelta(minutes=5)  # the longer backoff
    clock.seconds += 6  # more than our own 5 s, less than the 12 s the site asked for
    assert scheduler.pick([second]) == []
    clock.seconds += 6.5
    assert scheduler.pick([second]) == [second]


def test_an_unreachable_robots_txt_waits_without_counting_an_attempt() -> None:
    first = row(1, attempts=1)
    outcome = failure(FailureKind.robots_unreachable, BodyStatus.pending)
    worker, repo, _, _, _ = make([first], {first.url: outcome})
    run_pass(worker)
    (deferred,) = repo.stored("defer")
    assert deferred["next_attempt_at"] == NOW + timedelta(minutes=60)
    assert repo.stored("retry") == [] and repo.stored("final") == []


# ---------------------------------------------------------------- scheduling
def test_one_page_per_site_per_round_and_the_site_waits_afterwards() -> None:
    a1, a2, b1 = row(1, "a.example"), row(2, "a.example"), row(3, "b.example")
    results = {r.url: page(r.url) for r in (a1, a2, b1)}
    worker, repo, fetcher, _, clock = make([a1, a2, b1], results)
    run_pass(worker)
    assert sorted(fetcher.urls) == sorted([a1.url, b1.url])
    assert run_pass(worker).processed == 0  # both sites are still waiting
    clock.seconds += 5.1
    run_pass(worker)
    assert a2.url in fetcher.urls  # a.example may be asked again now


def test_a_crawl_delay_from_the_site_sets_how_long_it_waits() -> None:
    a1, a2 = row(1), row(2)
    worker, _, fetcher, _, clock = make(
        [a1, a2], {a1.url: page(a1.url, crawl_delay=20.0)}
    )
    run_pass(worker)
    clock.seconds += 19
    assert run_pass(worker).processed == 0
    clock.seconds += 2
    run_pass(worker)
    assert a2.url in fetcher.urls


def test_the_round_is_limited_by_the_concurrency() -> None:
    rows = [row(n, f"h{n}.example") for n in range(1, 21)]
    worker, _, fetcher, scheduler, _ = make(
        rows, {r.url: page(r.url) for r in rows}, concurrency=16
    )
    assert run_pass(worker).processed == 16
    assert len(fetcher.urls) == 16 and scheduler.in_flight() == 0


# ---------------------------------------------------------------- robustness
def test_an_unexpected_error_in_one_row_becomes_a_retry_and_frees_its_site() -> None:
    a, b = row(1, "a.example"), row(2, "b.example")
    worker, repo, _, scheduler, _ = make(
        [a, b], {a.url: RuntimeError("bug in the fetcher"), b.url: page(b.url)}
    )
    result = run_pass(worker)
    assert result.processed == 2
    assert [p["url_hash"] for p in repo.stored("ok")] == ["h2"]
    (retry,) = repo.stored("retry")
    assert retry["url_hash"] == "h1" and retry["status"] is BodyStatus.pending
    assert scheduler.in_flight() == 0


def test_a_lost_race_is_not_an_error() -> None:
    first = row(1)
    worker, repo, _, scheduler, _ = make([first], {first.url: page(first.url)})
    repo.race = True
    assert run_pass(worker).processed == 1
    assert scheduler.in_flight() == 0


def test_a_database_outage_propagates_and_frees_the_sites() -> None:
    worker, repo, _, _, _ = make([])
    repo.fail_discover = DbUnavailable("down")
    with pytest.raises(DbUnavailable):
        run_pass(worker)
    first = row(1)
    worker, repo, _, scheduler, _ = make([first], {first.url: page(first.url)})
    repo.fail_store = DbUnavailable("down")
    with pytest.raises(DbUnavailable):
        run_pass(worker)
    assert scheduler.in_flight() == 0


def test_extraction_runs_off_the_event_loop() -> None:
    """The CPU-bound call goes through the injected `extract` in a worker thread."""
    seen: list[str] = []

    def spy(html: str, url: str, **kw: int) -> Any:
        import threading  # noqa: PLC0415

        seen.append(threading.current_thread().name)
        from newsdock_extractor.domain.extract import extract_text  # noqa: PLC0415

        return extract_text(html, url, **kw)

    first = row(1)
    clock = Clock()
    scheduler: HostScheduler[QueueRow] = HostScheduler(
        clock=clock, per_host_delay=5.0, max_crawl_delay=30.0
    )
    worker = ExtractWorker(
        FakeRepo([first]),
        FakeFetcher({first.url: page(first.url)}),
        scheduler,
        WorkerConfig(
            batch_size=10,
            concurrency=4,
            retention_days=7,
            backfill_hours=6,
            min_chars=200,
            text_cap_chars=20_000,
            passage_chars=1000,
            passage_max_chars=1200,
            max_attempts=3,
            retry_backoff_minutes=(5, 30),
            max_crawl_delay_seconds=30.0,
            robots_failure_minutes=60,
        ),
        clock=lambda: NOW,
        extract=spy,
    )
    run_pass(worker)
    assert seen and all(name != "MainThread" for name in seen)
