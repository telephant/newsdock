"""TC-2 (fetcher level), TC-5, TC-7, TC-8, TC-11 (fetch half), TC-30: the fetcher
against local test servers. No real site is contacted; no Docker is needed.

`site` and the TLS factories come from `tests/conftest.py`; the address policy names the
local server's port and allows loopback, which no setting can do in production.
"""

import asyncio
import re
import ssl
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

import pytest
from newsdock_extractor.adapters.fetch import (
    FailureKind,
    FetchConfig,
    Fetched,
    Fetcher,
    FetchFailure,
    parse_retry_after,
)
from newsdock_extractor.adapters.resolve import AddressPolicy, ResolveError
from newsdock_extractor.adapters.robots import RobotsDecision
from newsdock_extractor.domain.status import BodyStatus

UA = "newsdock-extractor/0.1 (test; respects robots.txt)"
PAGE = (
    b"<html><head><title>t</title></head>"
    b"<body><article><p>Hello.</p></article></body></html>"
)
ALLOW_ALL = b"User-agent: *\nDisallow:\n"
NOW = datetime(2026, 10, 21, 7, 26, 0, tzinfo=UTC)


class TableResolver:
    """Names to addresses; `sequence` gives a different answer on each call."""

    def __init__(
        self, table: dict[str, list[str]] | list[dict[str, list[str]]]
    ) -> None:
        self.sequence = table if isinstance(table, list) else [table]
        self.calls: list[str] = []

    async def resolve(self, host: str) -> list[str]:
        step = self.sequence[min(len(self.calls), len(self.sequence) - 1)]
        self.calls.append(host)
        if host not in step:
            raise ResolveError(host)
        return step[host]


class AllowAllRobots:
    def __init__(self, crawl_delay: float | None = None) -> None:
        self.crawl_delay = crawl_delay

    async def check(self, url: str) -> RobotsDecision:
        return RobotsDecision(allowed=True, crawl_delay=self.crawl_delay)


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def make(
    site: Any,
    *,
    resolver: TableResolver | None = None,
    robots: AllowAllRobots | None = None,
    tls: ssl.SSLContext | None = None,
    extra_ports: tuple[int, ...] = (),
    **config: Any,
) -> Fetcher:
    names = {"site.test": ["127.0.0.1"], "other.test": ["127.0.0.1"]}
    base: dict[str, Any] = {
        "user_agent": UA,
        "connect_timeout_seconds": 2.0,
        "read_timeout_seconds": 0.6,
        "total_timeout_seconds": 3.0,
        "max_bytes": 50_000,
        "max_redirects": 3,
        "max_crawl_delay_seconds": 30.0,
        "robots_ttl_hours": 24,
        "robots_failure_minutes": 60,
    }
    base.update(config)
    return Fetcher(
        FetchConfig(**base),
        resolver=resolver or TableResolver(names),
        policy=AddressPolicy(
            allow_loopback=True, allowed_ports=(site.port, *extra_ports)
        ),
        robots=robots,
        tls_verify=tls if tls is not None else True,
        clock=lambda: NOW,
    )


def url(
    site: Any, path: str = "/a", host: str = "site.test", scheme: str = "http"
) -> str:
    return f"{scheme}://{host}:{site.port}{path}"


def fetch(fetcher: Fetcher, address: str) -> Fetched | FetchFailure:
    return run(fetcher.fetch(address))  # type: ignore[no-any-return]


def serve_page(site: Any, path: str = "/a") -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route(path, body=PAGE)


# ---------------------------------------------------------------------- TC-5
def test_robots_and_page_requests_carry_the_descriptive_headers(site: Any) -> None:
    serve_page(site)
    result = fetch(make(site), url(site))
    assert isinstance(result, Fetched), result
    for path, accepted in (("/robots.txt", "text/plain"), ("/a", "text/html")):
        (hit,) = site.hits(path)
        headers = hit["headers"]
        assert headers["user-agent"] == UA
        assert accepted in headers["accept"]
        assert headers["host"] == f"site.test:{site.port}"
        assert headers["accept-language"] == "en"
    assert result.http_status == 200 and result.body == PAGE


def test_the_agent_is_sent_on_every_redirect_hop(site: Any) -> None:
    serve_page(site, "/final")
    site.route("/a", status=302, headers={"Location": "/b"})
    site.route("/b", status=301, headers={"Location": "/final"})
    result = fetch(make(site), url(site))
    assert isinstance(result, Fetched) and result.final_url.endswith("/final")
    assert [
        h["headers"]["user-agent"] for h in site.requests if h["path"] != "/robots.txt"
    ] == [UA] * 3


# ---------------------------------------------------------------- TC-2 (fetcher level)
def test_a_robots_disallow_means_the_page_is_never_requested(site: Any) -> None:
    site.route(
        "/robots.txt", body=b"User-agent: *\nDisallow: /a\n", content_type="text/plain"
    )
    site.route("/a", body=PAGE)
    result = fetch(make(site), url(site))
    assert isinstance(result, FetchFailure)
    assert (result.kind, result.status) == (
        FailureKind.final,
        BodyStatus.blocked_robots,
    )
    assert site.hits("/a") == []
    assert len(site.hits("/robots.txt")) == 1


def test_a_crawl_delay_above_the_cap_is_blocked_without_a_page_request(
    site: Any,
) -> None:
    site.route(
        "/robots.txt",
        body=b"User-agent: *\nCrawl-delay: 60\n",
        content_type="text/plain",
    )
    site.route("/a", body=PAGE)
    result = fetch(make(site), url(site))
    assert (
        isinstance(result, FetchFailure) and result.status is BodyStatus.blocked_robots
    )
    assert "crawl-delay" in result.reason.lower()
    assert site.hits("/a") == []


def test_a_crawl_delay_within_the_cap_is_reported_for_the_scheduler(site: Any) -> None:
    site.route(
        "/robots.txt",
        body=b"User-agent: *\nCrawl-delay: 20\n",
        content_type="text/plain",
    )
    site.route("/a", body=PAGE)
    result = fetch(make(site), url(site))
    assert isinstance(result, Fetched) and result.crawl_delay == 20.0


def test_an_unreachable_robots_txt_waits_instead_of_fetching_blind(site: Any) -> None:
    site.route("/robots.txt", status=503, body=b"down", content_type="text/plain")
    site.route("/a", body=PAGE)
    result = fetch(make(site), url(site))
    assert isinstance(result, FetchFailure)
    assert result.kind is FailureKind.robots_unreachable
    assert site.hits("/a") == []


def test_a_missing_robots_txt_allows_everything(site: Any) -> None:
    site.route("/a", body=PAGE)  # /robots.txt answers 404
    assert isinstance(fetch(make(site), url(site)), Fetched)


def test_a_robots_txt_behind_a_redirect_is_followed(site: Any) -> None:
    site.route("/robots.txt", status=301, headers={"Location": "/real-robots"})
    site.route(
        "/real-robots", body=b"User-agent: *\nDisallow: /a\n", content_type="text/plain"
    )
    site.route("/a", body=PAGE)
    result = fetch(make(site), url(site))
    assert (
        isinstance(result, FetchFailure) and result.status is BodyStatus.blocked_robots
    )


# ---------------------------------------------------------------------- TC-7
def test_a_relative_redirect_is_followed(site: Any) -> None:
    serve_page(site, "/b")
    site.route("/a", status=302, headers={"Location": "/b"})
    result = fetch(make(site), url(site))
    assert isinstance(result, Fetched) and result.final_url == url(site, "/b")


def test_a_redirect_to_another_port_is_refused_and_the_target_never_contacted(
    site: Any, make_site: Callable[[], Any]
) -> None:
    victim = make_site()
    victim.route("/secret", body=b"internal data")
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route(
        "/a", status=302, headers={"Location": f"http://127.0.0.1:{victim.port}/secret"}
    )
    result = fetch(make(site), url(site))
    assert isinstance(result, FetchFailure)
    assert (result.kind, result.status) == (
        FailureKind.final,
        BodyStatus.blocked_address,
    )
    assert victim.requests == []


@pytest.mark.parametrize(
    "target",
    [
        "ftp://example.com/x",
        "file:///etc/passwd",
        "gopher://example.com/",
        "http://10.0.0.5/x",  # a private literal
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://[::1]/x",
        "http://user:pw@example.com/x",
        "http://example.com:8080/x",
    ],
)
def test_a_redirect_to_anything_unsafe_is_blocked_address(
    site: Any, target: str
) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", status=302, headers={"Location": target})
    result = fetch(make(site), url(site))
    assert isinstance(result, FetchFailure)
    assert result.status is BodyStatus.blocked_address, result


def test_a_redirect_without_a_target_is_an_http_error(site: Any) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", status=302)
    result = fetch(make(site), url(site))
    assert isinstance(result, FetchFailure)
    assert (result.kind, result.status) == (FailureKind.final, BodyStatus.http_error)


def test_too_many_redirects_end_as_an_http_error_after_the_limit(site: Any) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    for n in range(10):
        site.route(f"/r{n}", status=302, headers={"Location": f"/r{n + 1}"})
    result = fetch(make(site, max_redirects=3), url(site, "/r0"))
    assert isinstance(result, FetchFailure) and result.status is BodyStatus.http_error
    assert "redirect" in result.reason
    page_hits = [r for r in site.requests if re.fullmatch(r"/r\d+", str(r["path"]))]
    assert len(page_hits) == 4  # the first request and three redirects, no more


def test_a_redirect_to_another_host_is_checked_against_its_own_robots(
    site: Any,
) -> None:
    site.route(
        "/robots.txt", body=b"User-agent: *\nDisallow: /b\n", content_type="text/plain"
    )
    site.route(
        "/a", status=302, headers={"Location": f"http://other.test:{site.port}/b"}
    )
    site.route("/b", body=PAGE)
    result = fetch(make(site), url(site))
    assert (
        isinstance(result, FetchFailure) and result.status is BodyStatus.blocked_robots
    )
    assert site.hits("/b") == []


# ---------------------------------------------------------------------- TC-8
def test_the_checked_address_is_the_one_connected_to_and_there_is_one_lookup(
    site: Any,
) -> None:
    site.route("/a", body=PAGE)
    # a rebinding resolver: a usable first answer, a private one on the second call
    resolver = TableResolver(
        [{"site.test": ["127.0.0.1"]}, {"site.test": ["10.0.0.1"]}]
    )
    fetcher = make(site, resolver=resolver, robots=AllowAllRobots())
    first = fetch(fetcher, url(site))
    assert isinstance(first, Fetched)
    assert resolver.calls == ["site.test"]  # exactly one lookup for the request
    assert len(site.hits("/a")) == 1
    second = fetch(fetcher, url(site))  # the next lookup says private: refused
    assert (
        isinstance(second, FetchFailure) and second.status is BodyStatus.blocked_address
    )
    assert len(site.hits("/a")) == 1  # nothing was sent the second time


def test_a_name_that_resolves_to_a_private_address_is_never_connected_to(
    site: Any,
) -> None:
    site.route("/a", body=PAGE)
    resolver = TableResolver({"site.test": ["10.0.0.1"]})
    result = fetch(make(site, resolver=resolver), url(site))
    assert (
        isinstance(result, FetchFailure) and result.status is BodyStatus.blocked_address
    )
    assert resolver.calls == ["site.test"]  # no robots lookup either: refused first
    assert site.requests == []


def test_a_certificate_for_the_right_name_is_accepted_and_a_wrong_one_is_not(
    tls_site_factory: Callable[[str], Any], tls_client_context: ssl.SSLContext
) -> None:
    good = tls_site_factory("site.test")
    good.route("/a", body=PAGE)
    ok = fetch(
        make(good, robots=AllowAllRobots(), tls=tls_client_context),
        url(good, scheme="https"),
    )
    assert isinstance(ok, Fetched), ok

    wrong = tls_site_factory(
        "other.test"
    )  # the server holds a certificate for another name
    wrong.route("/a", body=PAGE)
    bad = fetch(
        make(wrong, robots=AllowAllRobots(), tls=tls_client_context),
        url(wrong, scheme="https"),  # ...but we ask for site.test
    )
    assert isinstance(bad, FetchFailure)
    assert bad.kind is FailureKind.transient
    assert "certificate" in bad.reason.lower()
    assert wrong.hits("/a") == []  # the handshake failed, nothing was sent


def test_an_untrusted_authority_is_refused_by_default(
    tls_site_factory: Callable[[str], Any],
) -> None:
    site = tls_site_factory("site.test")
    site.route("/a", body=PAGE)
    result = fetch(make(site, robots=AllowAllRobots()), url(site, scheme="https"))
    assert isinstance(result, FetchFailure) and "certificate" in result.reason.lower()


def test_a_connection_is_never_reused_for_another_name(
    tls_site_factory: Callable[[str], Any], tls_client_context: ssl.SSLContext
) -> None:
    """T-01 finding: a pooled connection to an IP skips the name check on reuse."""
    site = tls_site_factory("site.test")
    site.route("/a", body=PAGE)
    fetcher = make(site, robots=AllowAllRobots(), tls=tls_client_context)
    assert isinstance(
        fetch(fetcher, url(site, host="site.test", scheme="https")), Fetched
    )
    # same address and port, a name the certificate does not cover
    again = fetch(fetcher, url(site, host="other.test", scheme="https"))
    assert isinstance(again, FetchFailure), "the connection was reused without checking"
    assert "certificate" in again.reason.lower()


# ---------------------------------------------------------------- TC-11 (fetch half)
@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 451])
def test_other_4xx_are_final_http_errors_with_the_status(
    site: Any, status: int
) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", status=status, body=b"no")
    result = fetch(make(site), url(site))
    assert isinstance(result, FetchFailure)
    assert (result.kind, result.status, result.http_status) == (
        FailureKind.final,
        BodyStatus.http_error,
        status,
    )


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_429_and_5xx_are_transient(site: Any, status: int) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", status=status, body=b"later")
    result = fetch(make(site), url(site))
    assert isinstance(result, FetchFailure)
    assert result.kind is FailureKind.transient and result.http_status == status
    assert result.retry_after_seconds is None


def test_retry_after_in_seconds_and_as_a_date_is_reported(site: Any) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", status=429, headers={"Retry-After": "120"})
    seconds = fetch(make(site), url(site))
    assert isinstance(seconds, FetchFailure) and seconds.retry_after_seconds == 120.0
    site.route(
        "/b", status=429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
    )
    dated = fetch(make(site), url(site, "/b"))
    assert isinstance(dated, FetchFailure) and dated.retry_after_seconds == 120.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [("30", 30.0), ("0", 0.0), (" 7 ", 7.0), ("", None), ("soon", None), ("-5", None),
     ("Wed, 21 Oct 2026 07:26:00 GMT", 0.0), ("Wed, 21 Oct 2026 07:20:00 GMT", 0.0)],
)  # fmt: skip
def test_parse_retry_after(value: str, expected: float | None) -> None:
    assert parse_retry_after(value, NOW) == expected


def test_a_slow_answer_is_a_transient_timeout(site: Any) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", body=PAGE, delay=1.6)
    result = fetch(make(site, read_timeout_seconds=0.4), url(site))
    assert isinstance(result, FetchFailure) and result.kind is FailureKind.transient
    assert "timeout" in result.reason.lower()


def test_nothing_listening_is_a_transient_failure(site: Any, unused_port: int) -> None:
    fetcher = make(site, robots=AllowAllRobots(), extra_ports=(unused_port,))
    result = fetch(fetcher, f"http://site.test:{unused_port}/a")
    assert isinstance(result, FetchFailure) and result.kind is FailureKind.transient


def test_an_unresolvable_name_is_transient_not_blocked(site: Any) -> None:
    result = fetch(make(site, resolver=TableResolver({})), url(site))
    assert isinstance(result, FetchFailure)
    assert (
        result.kind is FailureKind.transient
        and result.status is not BodyStatus.blocked_address
    )


@pytest.mark.parametrize(
    "content_type", ["application/pdf", "image/png", "text/plain", None]
)
def test_anything_but_html_is_final_not_html(
    site: Any, content_type: str | None
) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", body=b"%PDF-1.7 not a page", content_type=content_type)
    result = fetch(make(site), url(site))
    assert isinstance(result, FetchFailure)
    assert (result.kind, result.status) == (FailureKind.final, BodyStatus.not_html)


def test_xhtml_counts_as_html(site: Any) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", body=PAGE, content_type="application/xhtml+xml; charset=utf-8")
    assert isinstance(fetch(make(site), url(site)), Fetched)


def test_a_body_over_the_cap_is_too_large_and_reading_stops(site: Any) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", body=b"x" * 400_000)
    result = fetch(make(site, max_bytes=50_000), url(site))
    assert isinstance(result, FetchFailure)
    assert (result.kind, result.status) == (FailureKind.final, BodyStatus.too_large)


def test_a_content_length_over_the_cap_is_refused_before_reading(site: Any) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", body=b"tiny", announce_length=10_000_000)
    result = fetch(make(site, max_bytes=50_000), url(site))
    assert isinstance(result, FetchFailure) and result.status is BodyStatus.too_large


def test_an_empty_200_is_a_page_with_no_bytes(site: Any) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", body=b"")
    result = fetch(make(site), url(site))
    assert isinstance(result, Fetched) and result.body == b""


def test_a_compressed_page_is_decoded_and_the_wire_size_is_smaller(site: Any) -> None:
    text = (
        b"<html><body><article>"
        + b"<p>The same sentence again.</p>" * 600
        + b"</article></body></html>"
    )
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", body=text, gzip_body=True)
    result = fetch(make(site, max_bytes=100_000), url(site))
    assert isinstance(result, Fetched)
    assert result.body == text
    assert 0 < result.wire_bytes < len(text) / 5


@pytest.mark.parametrize(
    ("content_type", "charset"),
    [
        ("text/html; charset=iso-8859-1", "iso-8859-1"),
        ('text/html; charset="UTF-8"', "utf-8"),
        ("text/html", None),
    ],
)
def test_the_charset_of_the_response_is_reported(
    site: Any, content_type: str, charset: str | None
) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", body=PAGE, content_type=content_type)
    result = fetch(make(site), url(site))
    assert isinstance(result, Fetched) and result.charset == charset


# ---------------------------------------------------------------------- TC-30
def test_no_cookie_is_ever_sent_back(site: Any) -> None:
    site.route("/robots.txt", body=ALLOW_ALL, content_type="text/plain")
    site.route("/a", body=PAGE, headers={"Set-Cookie": "session=abc; Path=/"})
    site.route("/b", body=PAGE)
    fetcher = make(site)
    assert isinstance(fetch(fetcher, url(site, "/a")), Fetched)
    assert isinstance(fetch(fetcher, url(site, "/b")), Fetched)
    assert all("cookie" not in hit["headers"] for hit in site.requests)


# a refused URL shape never reaches the network
@pytest.mark.parametrize(
    "address",
    ["http://user:pw@site.test/a", "ftp://site.test/a", "http://site.test:22/a"],
)
def test_unsafe_urls_are_blocked_before_any_lookup(site: Any, address: str) -> None:
    resolver = TableResolver({"site.test": ["127.0.0.1"]})
    result = fetch(make(site, resolver=resolver), address)
    assert (
        isinstance(result, FetchFailure) and result.status is BodyStatus.blocked_address
    )
    assert resolver.calls == [] and site.requests == []
