"""TC-1 (AC-1): robots.txt rules, statuses and caching."""

import asyncio
from datetime import datetime, timedelta

import pytest
from newsdock_extractor.adapters.robots import (
    RobotsCache,
    RobotsDecision,
    RobotsResponse,
)

UA = (
    "newsdock-extractor/0.1 (article text for a private news dock; respects robots.txt)"
)

SAMPLE = """\
User-agent: *
Disallow: /*/amp/
Disallow: /search?*q=
Disallow: /private$
Allow: /private/public
Crawl-delay: 7

User-agent: newsdock-extractor
Disallow: /no-extractor/
Crawl-delay: 20

User-agent: BadBot
Disallow: /
"""


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 2, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.now


class FakeGetter:
    """Scripted robots.txt answers per origin; records every request."""

    def __init__(self, answers: dict[str, RobotsResponse]) -> None:
        self.answers = answers
        self.calls: list[str] = []

    async def fetch_robots(self, origin: str) -> RobotsResponse:
        self.calls.append(origin)
        await asyncio.sleep(0)  # a real getter awaits the network
        return self.answers.get(origin, RobotsResponse(status=404, body=""))


def make(
    answers: dict[str, RobotsResponse], clock: Clock | None = None
) -> tuple[RobotsCache, FakeGetter, Clock]:
    clock = clock or Clock()
    getter = FakeGetter(answers)
    cache = RobotsCache(
        getter, user_agent=UA, ttl_hours=24, failure_minutes=60, clock=clock
    )
    return cache, getter, clock


def check(cache: RobotsCache, url: str) -> RobotsDecision:
    return asyncio.run(cache.check(url))


def serving(body: str, status: int = 200) -> dict[str, RobotsResponse]:
    return {"https://site.example": RobotsResponse(status=status, body=body)}


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("/news/story", True),
        ("/news/amp/story", True),  # the `*` group does not apply: ours does
        ("/no-extractor/page", False),  # our own group
        ("/", True),
    ],
)
def test_our_group_wins_over_the_star_group(path: str, allowed: bool) -> None:
    cache, _, _ = make(serving(SAMPLE))
    assert check(cache, f"https://site.example{path}").allowed is allowed


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("/news/story", True),
        ("/news/amp/story", False),  # wildcard in the middle
        ("/search?a=1&q=test", False),  # wildcard in the query
        ("/private", False),  # `$` means exactly this path
        ("/privateer", True),  # ... so a longer path is fine
        ("/private/public", True),  # the longer Allow wins
        ("/private/other", True),
    ],
)
def test_wildcards_dollar_and_longest_match_follow_the_standard(
    path: str, allowed: bool
) -> None:
    star_only = SAMPLE.split("User-agent: newsdock-extractor")[0]
    cache, _, _ = make(serving(star_only))
    assert check(cache, f"https://site.example{path}").allowed is allowed


def test_a_group_that_names_us_with_a_blanket_disallow() -> None:
    cache, _, _ = make(serving("User-agent: newsdock-extractor\nDisallow: /\n"))
    assert check(cache, "https://site.example/anything").allowed is False


def test_an_empty_disallow_allows_everything() -> None:
    cache, _, _ = make(serving("User-agent: *\nDisallow:\n"))
    assert check(cache, "https://site.example/x").allowed is True


def test_the_crawl_delay_of_our_group_else_of_the_star_group() -> None:
    cache, _, _ = make(serving(SAMPLE))
    assert check(cache, "https://site.example/a").crawl_delay == 20.0
    only_star = serving("User-agent: *\nCrawl-delay: 7\n")
    cache, _, _ = make(only_star)
    assert check(cache, "https://site.example/a").crawl_delay == 7.0
    cache, _, _ = make(serving("User-agent: *\nDisallow:\n"))
    assert check(cache, "https://site.example/a").crawl_delay is None


# how the status of the robots.txt request is read
@pytest.mark.parametrize("status", [401, 403])
def test_401_and_403_disallow_everything(status: int) -> None:
    cache, _, _ = make(serving("", status=status))
    decision = check(cache, "https://site.example/x")
    assert decision.allowed is False and decision.unreachable is False


@pytest.mark.parametrize("status", [404, 410, 400, 429, 451])
def test_other_4xx_allow_everything(status: int) -> None:
    cache, _, _ = make(serving("", status=status))
    decision = check(cache, "https://site.example/x")
    assert decision.allowed is True and decision.unreachable is False


@pytest.mark.parametrize("status", [500, 502, 503, None])
def test_5xx_and_unreachable_disallow_for_now_and_say_so(status: int | None) -> None:
    cache, _, _ = make(serving("", status=status))  # type: ignore[arg-type]
    decision = check(cache, "https://site.example/x")
    assert decision.allowed is False and decision.unreachable is True


def test_garbage_in_robots_txt_never_crashes_and_allows() -> None:
    cache, _, _ = make(serving("\x00\x01 not a robots file \xff<html>"))
    assert check(cache, "https://site.example/x").allowed is True


# caching
def test_a_good_robots_txt_is_fetched_once_and_kept_for_the_ttl() -> None:
    cache, getter, clock = make(serving(SAMPLE))

    async def three() -> None:
        for _ in range(3):
            await cache.check("https://site.example/a")

    asyncio.run(three())
    assert getter.calls == ["https://site.example"]
    clock.now += timedelta(hours=23, minutes=59)
    check(cache, "https://site.example/b")
    assert len(getter.calls) == 1
    clock.now += timedelta(minutes=2)
    check(cache, "https://site.example/c")
    assert len(getter.calls) == 2  # expired: read again


def test_a_failure_is_remembered_only_for_the_failure_window() -> None:
    cache, getter, clock = make(serving("", status=503))
    assert check(cache, "https://site.example/a").unreachable is True
    clock.now += timedelta(minutes=59)
    assert check(cache, "https://site.example/b").unreachable is True
    assert len(getter.calls) == 1
    clock.now += timedelta(minutes=2)
    getter.answers["https://site.example"] = RobotsResponse(status=200, body=SAMPLE)
    assert check(cache, "https://site.example/c").unreachable is False
    assert len(getter.calls) == 2


def test_concurrent_checks_of_one_site_share_one_request() -> None:
    cache, getter, _ = make(serving(SAMPLE))

    async def many() -> list[bool]:
        results = await asyncio.gather(
            *(cache.check(f"https://site.example/p{n}") for n in range(8))
        )
        return [r.allowed for r in results]

    assert all(asyncio.run(many()))
    assert getter.calls == ["https://site.example"]


def test_each_origin_has_its_own_robots_txt() -> None:
    answers = {
        "https://a.example": RobotsResponse(
            status=200, body="User-agent: *\nDisallow: /\n"
        ),
        "https://b.example": RobotsResponse(
            status=200, body="User-agent: *\nDisallow:\n"
        ),
        "http://a.example": RobotsResponse(status=404, body=""),
    }
    cache, getter, _ = make(answers)
    assert check(cache, "https://a.example/x").allowed is False
    assert check(cache, "https://b.example/x").allowed is True
    assert check(cache, "http://a.example/x").allowed is True  # another origin
    assert sorted(getter.calls) == [
        "http://a.example",
        "https://a.example",
        "https://b.example",
    ]


def test_the_origin_is_lower_cased_and_without_the_path() -> None:
    cache, getter, _ = make({})
    check(cache, "https://Site.Example/Some/Path?x=1")
    assert getter.calls == ["https://site.example"]
