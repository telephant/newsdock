"""Per-site scheduling: one request per site at a time, spaced by a delay (ADR-0035).

In memory, with an injected clock. A round takes at most one row per site, only for
sites that are not being fetched and whose delay has elapsed. After a fetch the caller
reports the site's next delay (its own configured delay, or its `Crawl-delay`).
A restart forgets everything: the first request to each site is then immediate.
"""

from collections.abc import Callable, Sequence
from typing import Protocol
from urllib.parse import urlsplit


class HasUrl(Protocol):
    @property
    def url(self) -> str: ...


def host_of(url: str) -> str:
    """The lower-cased host name of a URL, without port."""
    return (urlsplit(url).hostname or "").lower()


class HostScheduler[R: HasUrl]:
    def __init__(
        self,
        *,
        clock: Callable[[], float],
        per_host_delay: float,
        max_crawl_delay: float,
    ) -> None:
        self._clock = clock
        self._per_host_delay = per_host_delay
        self._max_crawl_delay = max_crawl_delay
        self._next_allowed: dict[str, float] = {}
        self._in_flight: set[str] = set()

    def pick(self, rows: Sequence[R], *, limit: int | None = None) -> list[R]:
        """The first row of each ready site, in the order given, at most `limit`.

        The sites picked count as in flight until `finish` is called for them."""
        now = self._clock()
        chosen: list[R] = []
        seen: set[str] = set()
        for row in rows:
            if limit is not None and len(chosen) >= limit:
                break
            host = host_of(row.url)
            if host in seen or host in self._in_flight:
                continue
            seen.add(host)
            if self._next_allowed.get(host, 0.0) > now:
                continue
            self._in_flight.add(host)
            chosen.append(row)
        return chosen

    def finish(self, host: str, *, delay: float) -> None:
        """The fetch for `host` is over; it may be asked again after `delay` seconds."""
        self._in_flight.discard(host)
        self._next_allowed[host] = self._clock() + delay

    def in_flight(self) -> int:
        return len(self._in_flight)

    def delay_for(self, crawl_delay: float | None) -> float | None:
        """The delay a site gets: our own, or its Crawl-delay when that is longer.

        None when the site asks for more than the cap: it is skipped, not crawled
        faster than it wants."""
        if crawl_delay is not None and crawl_delay > self._max_crawl_delay:
            return None
        return max(self._per_host_delay, crawl_delay or 0.0)
