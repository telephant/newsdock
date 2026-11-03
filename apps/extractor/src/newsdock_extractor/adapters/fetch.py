"""The page fetcher (ADR-0035, design-detail.md section 4).

For one URL: the address guard, then robots.txt (per site, again after a redirect
to another site), then a request that connects to the address the guard checked, with
the site's name for TLS (`sni_hostname`), on a brand-new connection every time (T-01: a
pooled connection to an IP is reused without checking the claimed name again).
Redirects are followed by hand, each hop checked again. The body is streamed under a
byte cap, only HTML is accepted, and a fresh client means no cookie is ever kept or
sent back. Every outcome is a `Fetched` or a `FetchFailure` that says whether it is
final, transient (retry later) or a wait for an unreachable robots.txt.
"""

import asyncio
import email.utils
import re
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from newsdock_extractor.adapters.resolve import (
    AddressPolicy,
    Allowed,
    Refused,
    Resolver,
    guard,
)
from newsdock_extractor.adapters.robots import (
    RobotsCache,
    RobotsDecision,
    RobotsResponse,
    origin_of,
)
from newsdock_extractor.config import Settings
from newsdock_extractor.domain.results import FailureKind, Fetched, FetchFailure
from newsdock_extractor.domain.status import BodyStatus

__all__ = [
    "FailureKind",
    "FetchConfig",
    "FetchFailure",
    "Fetched",
    "Fetcher",
    "RobotsChecker",
    "parse_retry_after",
]

ROBOTS_MAX_BYTES = 500_000
HTML_TYPES = ("text/html", "application/xhtml+xml")
_CHARSET = re.compile(r"charset\s*=\s*\"?([^\";\s]+)", re.IGNORECASE)


@dataclass(frozen=True)
class FetchConfig:
    user_agent: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    total_timeout_seconds: float
    max_bytes: int
    max_redirects: int
    max_crawl_delay_seconds: float
    robots_ttl_hours: float
    robots_failure_minutes: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "FetchConfig":
        return cls(
            user_agent=settings.user_agent,
            connect_timeout_seconds=settings.connect_timeout_seconds,
            read_timeout_seconds=settings.read_timeout_seconds,
            total_timeout_seconds=settings.total_timeout_seconds,
            max_bytes=settings.max_bytes,
            max_redirects=settings.max_redirects,
            max_crawl_delay_seconds=settings.max_crawl_delay_seconds,
            robots_ttl_hours=settings.robots_ttl_hours,
            robots_failure_minutes=settings.robots_failure_minutes,
        )


class RobotsChecker(Protocol):
    async def check(self, url: str) -> RobotsDecision: ...


@dataclass
class _Raw:
    status: int
    headers: httpx.Headers
    body: bytes
    wire_bytes: int
    not_html: bool = False
    too_large: bool = False


def parse_retry_after(value: str | None, now: datetime) -> float | None:
    """Seconds to wait from a `Retry-After` header (a number or an HTTP date)."""
    if not value or not value.strip():
        return None
    text = value.strip()
    if text.isdigit():
        return float(int(text))
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now).total_seconds())


def _charset(content_type: str) -> str | None:
    found = _CHARSET.search(content_type)
    return found.group(1).lower() if found else None


class Fetcher:
    def __init__(
        self,
        config: FetchConfig,
        *,
        resolver: Resolver,
        policy: AddressPolicy | None = None,
        robots: RobotsChecker | None = None,
        tls_verify: ssl.SSLContext | bool = True,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._cfg = config
        self._resolver = resolver
        self._policy = policy or AddressPolicy()
        self._tls_verify = tls_verify
        self._clock = clock
        self._robots: RobotsChecker = robots or RobotsCache(
            self,
            user_agent=config.user_agent,
            ttl_hours=config.robots_ttl_hours,
            failure_minutes=config.robots_failure_minutes,
            clock=clock,
        )

    # ------------------------------------------------------------------ the page
    async def fetch(self, url: str) -> Fetched | FetchFailure:
        current = url
        checked: set[str] = set()
        crawl_delay: float | None = None
        for _hop in range(self._cfg.max_redirects + 1):
            verdict = await guard(current, self._resolver, self._policy)
            if isinstance(verdict, Refused):
                return FetchFailure(
                    FailureKind.final, BodyStatus.blocked_address, verdict.reason
                )
            if not isinstance(verdict, Allowed):
                return FetchFailure(
                    FailureKind.transient, BodyStatus.failed, verdict.reason
                )
            origin = origin_of(current)
            if origin not in checked:
                checked.add(origin)
                decision = await self._robots.check(current)
                if decision.unreachable:
                    return FetchFailure(
                        FailureKind.robots_unreachable,
                        BodyStatus.pending,
                        "robots.txt unreachable",
                    )
                if not decision.allowed:
                    return FetchFailure(
                        FailureKind.final,
                        BodyStatus.blocked_robots,
                        "robots.txt disallows",
                    )
                crawl_delay = decision.crawl_delay
                if (
                    crawl_delay is not None
                    and crawl_delay > self._cfg.max_crawl_delay_seconds
                ):
                    return FetchFailure(
                        FailureKind.final,
                        BodyStatus.blocked_robots,
                        f"crawl-delay {crawl_delay:g}s above the cap",
                        crawl_delay=crawl_delay,
                    )
            raw = await self._send(
                current,
                verdict.address,
                accept="text/html,application/xhtml+xml",
                max_bytes=self._cfg.max_bytes,
                html_only=True,
            )
            if isinstance(raw, FetchFailure):
                return _with_delay(raw, crawl_delay)
            if 300 <= raw.status < 400:
                location = raw.headers.get("location")
                if not location:
                    return FetchFailure(
                        FailureKind.final,
                        BodyStatus.http_error,
                        "redirect without a target",
                        http_status=raw.status,
                        crawl_delay=crawl_delay,
                    )
                current = urljoin(current, location)
                continue
            return self._outcome(raw, current, crawl_delay)
        return FetchFailure(
            FailureKind.final,
            BodyStatus.http_error,
            f"too many redirects (more than {self._cfg.max_redirects})",
            crawl_delay=crawl_delay,
        )

    def _outcome(
        self, raw: _Raw, url: str, crawl_delay: float | None
    ) -> Fetched | FetchFailure:
        status = raw.status
        if status == 429 or status >= 500:
            return FetchFailure(
                FailureKind.transient,
                BodyStatus.failed,
                f"HTTP {status}",
                http_status=status,
                retry_after_seconds=parse_retry_after(
                    raw.headers.get("retry-after"), self._clock()
                ),
                crawl_delay=crawl_delay,
            )
        if status >= 400:
            return FetchFailure(
                FailureKind.final,
                BodyStatus.http_error,
                f"HTTP {status}",
                http_status=status,
                crawl_delay=crawl_delay,
            )
        if not 200 <= status < 300:
            return FetchFailure(
                FailureKind.transient, BodyStatus.failed, f"unexpected HTTP {status}",
                http_status=status, crawl_delay=crawl_delay,
            )  # fmt: skip
        if raw.not_html:
            return FetchFailure(
                FailureKind.final, BodyStatus.not_html, "not an HTML page",
                http_status=status, crawl_delay=crawl_delay,
            )  # fmt: skip
        if raw.too_large:
            return FetchFailure(
                FailureKind.final, BodyStatus.too_large,
                f"more than {self._cfg.max_bytes} bytes",
                http_status=status, crawl_delay=crawl_delay,
            )  # fmt: skip
        return Fetched(
            body=raw.body,
            final_url=url,
            http_status=status,
            wire_bytes=raw.wire_bytes,
            charset=_charset(raw.headers.get("content-type", "")),
            crawl_delay=crawl_delay,
        )

    # ------------------------------------------------------------------ robots.txt
    async def fetch_robots(self, origin: str) -> RobotsResponse:
        """The robots.txt of a site, through the same guard and pinned connection.

        No robots check for robots.txt itself; redirects are followed (guarded) up to
        the limit; any trouble reads as "no answer"."""
        current = f"{origin}/robots.txt"
        for _hop in range(self._cfg.max_redirects + 1):
            verdict = await guard(current, self._resolver, self._policy)
            if not isinstance(verdict, Allowed):
                return RobotsResponse(status=None, body="")
            raw = await self._send(
                current,
                verdict.address,
                accept="text/plain,*/*;q=0.1",
                max_bytes=ROBOTS_MAX_BYTES,
                html_only=False,
            )
            if isinstance(raw, FetchFailure):
                return RobotsResponse(status=None, body="")
            if 300 <= raw.status < 400 and raw.headers.get("location"):
                current = urljoin(current, raw.headers["location"])
                continue
            text = (
                raw.body.decode("utf-8", errors="replace")
                if 200 <= raw.status < 300
                else ""
            )
            return RobotsResponse(status=raw.status, body=text)
        return RobotsResponse(status=None, body="")

    # ------------------------------------------------------------------ one request
    async def _send(
        self, url: str, address: str, *, accept: str, max_bytes: int, html_only: bool
    ) -> _Raw | FetchFailure:
        parts = urlsplit(url)
        pinned = f"[{address}]" if ":" in address else address
        netloc = f"{pinned}:{parts.port}" if parts.port else pinned
        target = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
        headers = {
            "Host": parts.netloc,
            "User-Agent": self._cfg.user_agent,
            "Accept": accept,
            "Accept-Language": "en",
        }
        extensions = {"sni_hostname": parts.hostname} if parts.scheme == "https" else {}
        timeout = httpx.Timeout(
            connect=self._cfg.connect_timeout_seconds,
            read=self._cfg.read_timeout_seconds,
            write=self._cfg.read_timeout_seconds,
            pool=self._cfg.connect_timeout_seconds,
        )
        try:
            async with asyncio.timeout(self._cfg.total_timeout_seconds):
                # a new client for every request: no pooled connection, no cookie jar
                async with httpx.AsyncClient(
                    follow_redirects=False,
                    trust_env=False,
                    verify=self._tls_verify,
                    timeout=timeout,
                    limits=httpx.Limits(max_keepalive_connections=0),
                ) as client:
                    async with client.stream(
                        "GET", target, headers=headers, extensions=extensions
                    ) as response:
                        return await _read(response, max_bytes, html_only)
        except TimeoutError:
            return _transient("timeout")
        except httpx.TimeoutException:
            return _transient("timeout")
        except httpx.HTTPError as exc:
            if "CERTIFICATE" in str(exc).upper():
                return _transient("certificate verification failed")
            return _transient(f"{type(exc).__name__}")
        except OSError as exc:
            return _transient(f"{type(exc).__name__}")


async def _read(response: httpx.Response, max_bytes: int, html_only: bool) -> _Raw:
    status = response.status_code
    if status >= 300:  # redirects and errors: the body is not needed
        return _Raw(status, response.headers, b"", response.num_bytes_downloaded)
    if html_only:
        kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if kind not in HTML_TYPES:
            return _Raw(status, response.headers, b"", 0, not_html=True)
    announced = response.headers.get("content-length", "")
    if announced.isdigit() and int(announced) > max_bytes:
        return _Raw(status, response.headers, b"", 0, too_large=True)
    body = bytearray()
    too_large = False
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > max_bytes:
            too_large = True
            del body[max_bytes:]
            break
    return _Raw(
        status,
        response.headers,
        bytes(body),
        response.num_bytes_downloaded,
        too_large=too_large,
    )


def _transient(reason: str) -> FetchFailure:
    return FetchFailure(FailureKind.transient, BodyStatus.failed, reason)


def _with_delay(failure: FetchFailure, crawl_delay: float | None) -> FetchFailure:
    return FetchFailure(
        failure.kind,
        failure.status,
        failure.reason,
        failure.http_status,
        failure.retry_after_seconds,
        crawl_delay,
    )
