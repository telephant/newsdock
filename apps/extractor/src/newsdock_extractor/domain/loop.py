"""The extractor worker (design-detail.md section 3).

One pass: discover new articles, read the due rows newest first, take at most one row
per site, fetch them at once, extract the text and store one outcome per row: `ok` with
its passages, a final status, a retry, or a wait. Every picked site is released again
whatever happens, and one row's bug becomes a retry of that row, never a crash. A
database outage is the only error that leaves the pass (the caller backs off).

The repository, the fetcher and the clock are ports: the worker does no I/O of its own.
Repository calls and the CPU-bound extraction run in threads so the event loop stays
free for the other fetches.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from newsdock_extractor.domain.extract import ExtractResult, extract_text
from newsdock_extractor.domain.passages import split_passages
from newsdock_extractor.domain.picking import QueueRow
from newsdock_extractor.domain.results import FailureKind, Fetched, FetchFailure
from newsdock_extractor.domain.retry import after_transient_failure
from newsdock_extractor.domain.schedule import HostScheduler, host_of
from newsdock_extractor.domain.status import BodyStatus

logger = logging.getLogger(__name__)


class DbUnavailable(Exception):
    """A connection-level database failure: back off and run the pass again."""


class BodyRepo(Protocol):
    def discover(self, *, now: datetime, backfill_hours: int) -> int: ...

    def next_batch(
        self, *, now: datetime, retention_days: int, limit: int
    ) -> list[QueueRow]: ...

    def store_ok(
        self,
        url_hash: str,
        *,
        text: str,
        passages: list[str],
        http_status: int,
        fetched_at: datetime,
        attempts: int,
    ) -> bool: ...

    def store_final(
        self,
        url_hash: str,
        *,
        status: BodyStatus,
        http_status: int | None,
        fetched_at: datetime,
        attempts: int,
    ) -> bool: ...

    def store_retry(
        self,
        url_hash: str,
        *,
        status: BodyStatus,
        attempts: int,
        next_attempt_at: datetime | None,
        http_status: int | None,
    ) -> bool: ...

    def defer(self, url_hash: str, *, next_attempt_at: datetime) -> bool: ...


class PageFetcher(Protocol):
    async def fetch(self, url: str) -> Fetched | FetchFailure: ...


@dataclass(frozen=True)
class WorkerConfig:
    batch_size: int
    concurrency: int
    retention_days: int
    backfill_hours: int
    min_chars: int
    text_cap_chars: int
    passage_chars: int
    passage_max_chars: int
    max_attempts: int
    retry_backoff_minutes: tuple[int, ...]
    max_crawl_delay_seconds: float
    robots_failure_minutes: float


@dataclass(frozen=True)
class PassResult:
    processed: int  # rows worked on; 0 means nothing was due or every site is waiting


def decode_body(body: bytes, charset: str | None) -> str:
    """HTML bytes as text: the response's charset, else UTF-8; never raises."""
    try:
        return body.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class _Extracted:
    """A fetched page together with the result of extracting its text."""

    page: Fetched
    result: ExtractResult

    @property
    def crawl_delay(self) -> float | None:
        return self.page.crawl_delay


class ExtractWorker:
    def __init__(
        self,
        repo: BodyRepo,
        fetcher: PageFetcher,
        scheduler: HostScheduler[QueueRow],
        config: WorkerConfig,
        *,
        clock: Callable[[], datetime],
        extract: Callable[..., ExtractResult] = extract_text,
    ) -> None:
        self._repo = repo
        self._fetcher = fetcher
        self._scheduler = scheduler
        self._cfg = config
        self._clock = clock
        self._extract = extract

    async def run_pass(self) -> PassResult:
        now = self._clock()
        await asyncio.to_thread(
            self._repo.discover, now=now, backfill_hours=self._cfg.backfill_hours
        )
        rows = await asyncio.to_thread(
            self._repo.next_batch,
            now=now,
            retention_days=self._cfg.retention_days,
            limit=self._cfg.batch_size,
        )
        picked = self._scheduler.pick(rows, limit=self._cfg.concurrency)
        results = await asyncio.gather(
            *(self._process(row) for row in picked), return_exceptions=True
        )
        for result in results:  # only a database outage escapes `_process`
            if isinstance(result, BaseException):
                raise result
        return PassResult(processed=len(picked))

    async def _process(self, row: QueueRow) -> None:
        host = host_of(row.url)
        delay = self._site_delay(None)
        try:
            outcome = await self._fetch(row)
            delay = self._site_delay(outcome.crawl_delay)
            delay = max(delay, await self._store(row, outcome))
        finally:
            self._scheduler.finish(host, delay=delay)

    def _site_delay(self, crawl_delay: float | None) -> float:
        """The wait before the site is asked again (the cap for a site above it)."""
        return (
            self._scheduler.delay_for(crawl_delay) or self._cfg.max_crawl_delay_seconds
        )

    async def _fetch(self, row: QueueRow) -> Fetched | FetchFailure | _Extracted:
        try:
            outcome = await self._fetcher.fetch(row.url)
            if isinstance(outcome, FetchFailure):
                return outcome
            html = decode_body(outcome.body, outcome.charset)
            extracted = await asyncio.to_thread(
                self._extract,
                html,
                row.url,
                min_chars=self._cfg.min_chars,
                text_cap_chars=self._cfg.text_cap_chars,
            )
            return _Extracted(outcome, extracted)
        except DbUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001  one row's bug must not stop the pass
            logger.exception("row %s: unexpected error, will retry", row.url_hash)
            return FetchFailure(
                FailureKind.transient,
                BodyStatus.failed,
                f"unexpected {type(exc).__name__}",
            )

    async def _store(self, row: QueueRow, outcome: Any) -> float:
        """Write the outcome; returns extra wait for the site (0 when none)."""
        now = self._clock()
        attempts = row.attempts + 1
        if isinstance(outcome, _Extracted):
            page, extracted = outcome.page, outcome.result
            if extracted.status is BodyStatus.ok and extracted.text is not None:
                passages = split_passages(
                    extracted.text,
                    target=self._cfg.passage_chars,
                    hard_max=self._cfg.passage_max_chars,
                )
                await asyncio.to_thread(
                    self._repo.store_ok,
                    row.url_hash,
                    text=extracted.text,
                    passages=passages,
                    http_status=page.http_status,
                    fetched_at=now,
                    attempts=attempts,
                )
            else:
                await asyncio.to_thread(
                    self._repo.store_final,
                    row.url_hash,
                    status=extracted.status,
                    http_status=page.http_status,
                    fetched_at=now,
                    attempts=attempts,
                )
            return 0.0
        if outcome.kind is FailureKind.final:
            await asyncio.to_thread(
                self._repo.store_final,
                row.url_hash,
                status=outcome.status,
                http_status=outcome.http_status,
                fetched_at=now,
                attempts=attempts,
            )
            return 0.0
        if outcome.kind is FailureKind.robots_unreachable:
            await asyncio.to_thread(
                self._repo.defer,
                row.url_hash,
                next_attempt_at=now
                + timedelta(minutes=self._cfg.robots_failure_minutes),
            )
            return 0.0
        state = after_transient_failure(
            attempts=row.attempts,
            now=now,
            backoff_minutes=self._cfg.retry_backoff_minutes,
            max_attempts=self._cfg.max_attempts,
            max_site_delay_seconds=self._cfg.max_crawl_delay_seconds,
            retry_after_seconds=outcome.retry_after_seconds,
        )
        await asyncio.to_thread(
            self._repo.store_retry,
            row.url_hash,
            status=state.status,
            attempts=state.attempts,
            next_attempt_at=state.next_attempt_at,
            http_status=outcome.http_status,
        )
        return state.host_delay_seconds or 0.0


class PassWorker(Protocol):
    async def run_pass(self) -> "PassResult": ...


async def run(
    worker: PassWorker,
    *,
    poll_interval: float,
    backoff_base: float,
    backoff_cap: float,
    sleep: Callable[[float], Awaitable[None]],
    beat: Callable[[], None],
    should_stop: Callable[[], bool],
) -> None:
    """Run passes until `should_stop`: no wait after a busy pass, `poll_interval` after
    an idle one, a growing wait (capped) after a failed pass. The heartbeat is written
    after every pass, so a database outage does not make the container unhealthy."""
    failures = 0
    while not should_stop():
        try:
            result = await worker.run_pass()
        except asyncio.CancelledError:
            raise
        except DbUnavailable as exc:
            logger.warning("database unavailable, backing off: %s", exc)
            failed = True
        except Exception:  # noqa: BLE001  keep the worker alive, rows stay pending
            logger.exception("pass failed, backing off")
            failed = True
        else:
            failed = False
        beat()
        if failed:
            await sleep(min(backoff_cap, backoff_base * 2**failures))
            failures += 1
            continue
        failures = 0
        if result.processed == 0:
            await sleep(poll_interval)
