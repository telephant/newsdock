"""robots.txt decisions with a per-site cache (ADR-0035).

Parsed with Protego, which follows the standard (wildcards, `$`, longest match, groups);
Python's `urllib.robotparser` does not and is not used. How the answer to the
`/robots.txt` request is read: 401/403 disallow everything, another 4xx allows
everything, 5xx or no answer disallow for now (`unreachable`: try again later), 2xx is
parsed. Good answers are kept for `ttl_hours`, failures for `failure_minutes`. One
request serves all concurrent checks of a site. The request itself is made by a
`RobotsGetter` (the fetcher, through the address guard).
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from urllib.parse import urlsplit

from protego import Protego


@dataclass(frozen=True)
class RobotsResponse:
    status: int | None  # None: no answer (timeout, connection error, refused address)
    body: str


class RobotsGetter(Protocol):
    async def fetch_robots(self, origin: str) -> RobotsResponse: ...


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    crawl_delay: float | None = None
    unreachable: bool = False  # robots.txt could not be read: retry later


@dataclass
class _Entry:
    parser: Protego | None  # None for the disallow-all, allow-all and failure cases
    allow_all: bool
    unreachable: bool
    expires: datetime


def product_token(user_agent: str) -> str:
    """`newsdock-extractor/0.1 (...)` -> `newsdock-extractor`, the name a robots.txt
    group addresses."""
    return user_agent.split("/", 1)[0].split()[0] if user_agent.strip() else "*"


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{(parts.netloc or '').lower()}"


class RobotsCache:
    def __init__(
        self,
        getter: RobotsGetter,
        *,
        user_agent: str,
        ttl_hours: float,
        failure_minutes: float,
        clock: Callable[[], datetime],
    ) -> None:
        self._getter = getter
        self._token = product_token(user_agent)
        self._ttl = timedelta(hours=ttl_hours)
        self._failure = timedelta(minutes=failure_minutes)
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def check(self, url: str) -> RobotsDecision:
        origin = origin_of(url)
        entry = self._fresh(origin)
        if entry is None:
            lock = self._locks.setdefault(origin, asyncio.Lock())
            async with lock:
                entry = self._fresh(origin)
                if entry is None:
                    entry = await self._load(origin)
        return self._decide(entry, url)

    def _fresh(self, origin: str) -> _Entry | None:
        entry = self._entries.get(origin)
        if entry is not None and entry.expires > self._clock():
            return entry
        return None

    async def _load(self, origin: str) -> _Entry:
        response = await self._getter.fetch_robots(origin)
        now = self._clock()
        status = response.status
        if status is None or status >= 500:
            entry = _Entry(
                None, allow_all=False, unreachable=True, expires=now + self._failure
            )
        elif status in (401, 403):
            entry = _Entry(
                None, allow_all=False, unreachable=False, expires=now + self._ttl
            )
        elif status >= 400:
            entry = _Entry(
                None, allow_all=True, unreachable=False, expires=now + self._ttl
            )
        else:
            entry = _Entry(
                Protego.parse(response.body),
                allow_all=False,
                unreachable=False,
                expires=now + self._ttl,
            )
        self._entries[origin] = entry
        return entry

    def _decide(self, entry: _Entry, url: str) -> RobotsDecision:
        if entry.unreachable:
            return RobotsDecision(allowed=False, unreachable=True)
        if entry.parser is None:
            return RobotsDecision(allowed=entry.allow_all)
        delay = entry.parser.crawl_delay(self._token)
        return RobotsDecision(
            allowed=bool(entry.parser.can_fetch(url, self._token)),
            crawl_delay=float(delay) if delay else None,
        )
