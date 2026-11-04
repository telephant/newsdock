"""TC-3, TC-4 (AC-2): one request per site at a time, spaced by the delay."""

from dataclasses import dataclass

import pytest
from newsdock_extractor.domain.schedule import HostScheduler, host_of


@dataclass(frozen=True)
class Row:
    url: str


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def make(clock: Clock) -> HostScheduler[Row]:
    return HostScheduler(clock=clock, per_host_delay=5.0, max_crawl_delay=30.0)


A1, A2, A3 = (Row(f"https://a.example/story-{n}") for n in (1, 2, 3))
B1, B2 = Row("https://b.example/one"), Row("https://b.example/two")


def test_host_is_the_lower_cased_name_without_port() -> None:
    assert host_of("https://News.Example.COM:443/a?b=1") == "news.example.com"
    assert host_of("http://a.example/x") == "a.example"


# TC-3: at most one row per host and round, in the order given
def test_a_round_takes_the_first_row_of_each_host_only() -> None:
    scheduler = make(Clock())
    assert scheduler.pick([A1, A2, B1, A3, B2]) == [A1, B1]


def test_a_host_in_flight_is_not_picked_again() -> None:
    scheduler = make(Clock())
    assert scheduler.pick([A1, A2, B1]) == [A1, B1]
    assert scheduler.pick([A2, B2]) == []  # both still being fetched


def test_a_host_waits_for_its_delay_after_a_fetch_and_others_do_not() -> None:
    clock = Clock()
    scheduler = make(clock)
    assert scheduler.pick([A1, B1]) == [A1, B1]
    clock.now += 1
    scheduler.finish("a.example", delay=5.0)
    scheduler.finish("b.example", delay=1.0)  # a site with a short delay
    clock.now += 1  # t+2: a must wait until t+6, b may go at t+2
    assert scheduler.pick([A2, B2]) == [B2]
    clock.now += 3.9  # t+5.9
    assert scheduler.pick([A2]) == []
    clock.now += 0.2  # t+6.1
    assert scheduler.pick([A2]) == [A2]


def test_other_hosts_are_never_held_up_by_a_slow_one() -> None:
    clock = Clock()
    scheduler = make(clock)
    scheduler.pick([A1])
    scheduler.finish("a.example", delay=600.0)
    for _ in range(3):
        clock.now += 10
        assert scheduler.pick([A2, B1]) == [B1]
        scheduler.finish("b.example", delay=5.0)
        clock.now += 5
        assert scheduler.pick([A2]) == []


def test_the_limit_caps_the_round() -> None:
    scheduler = make(Clock())
    rows = [Row(f"https://h{n}.example/x") for n in range(10)]
    assert scheduler.pick(rows, limit=4) == rows[:4]
    assert scheduler.in_flight() == 4
    assert scheduler.pick(rows, limit=4) == rows[4:8]  # the first four are in flight


def test_finish_without_a_pick_is_harmless() -> None:
    clock = Clock()
    scheduler = make(clock)
    scheduler.finish("unknown.example", delay=5.0)
    assert scheduler.pick([Row("https://unknown.example/x")]) == []
    clock.now += 5.1
    assert scheduler.pick([Row("https://unknown.example/x")]) != []


# TC-4: the delay a site gets, with its Crawl-delay
@pytest.mark.parametrize(
    ("crawl_delay", "expected"),
    [
        (None, 5.0),  # nothing declared: the configured delay
        (0.0, 5.0),
        (3.0, 5.0),  # never faster than our own delay
        (7.0, 7.0),
        (20.0, 20.0),
        (30.0, 30.0),  # exactly the cap is still honoured
        (30.5, None),  # above the cap: the site is skipped, not crawled faster
        (60.0, None),
    ],
)
def test_delay_for_honours_crawl_delay_up_to_the_cap(
    crawl_delay: float | None, expected: float | None
) -> None:
    assert make(Clock()).delay_for(crawl_delay) == expected


def test_a_crawl_delay_of_twenty_keeps_the_site_waiting_twenty_seconds() -> None:
    clock = Clock()
    scheduler = make(clock)
    scheduler.pick([A1])
    delay = scheduler.delay_for(20.0)
    assert delay == 20.0
    scheduler.finish("a.example", delay=delay)
    clock.now += 19.9
    assert scheduler.pick([A2]) == []
    clock.now += 0.2
    assert scheduler.pick([A2]) == [A2]
