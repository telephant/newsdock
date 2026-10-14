"""TC-12 (AC-11, D-8): fixed-window limiter with a fake clock."""

from newsdock_api.domain.ratelimit import ANONYMOUS_BUCKET, FixedWindowLimiter


class Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_allows_n_then_denies_with_retry_after() -> None:
    clock = Clock(1020.0)  # 20 s into the window starting at 1020 // 60 * 60 = 1020
    limiter = FixedWindowLimiter(limit=3, clock=clock)
    assert all(limiter.allow("alpha").allowed for _ in range(3))
    denied = limiter.allow("alpha")
    assert not denied.allowed
    assert 1 <= denied.retry_after <= 60


def test_retry_after_is_time_to_window_end() -> None:
    clock = Clock(1000.0)  # window [960, 1020): 20 s left
    limiter = FixedWindowLimiter(limit=1, clock=clock)
    limiter.allow("a")
    assert limiter.allow("a").retry_after == 20


def test_window_rollover_resets() -> None:
    clock = Clock(1000.0)
    limiter = FixedWindowLimiter(limit=1, clock=clock)
    assert limiter.allow("a").allowed
    assert not limiter.allow("a").allowed
    clock.now = 1021.0  # next window
    assert limiter.allow("a").allowed


def test_agents_are_isolated() -> None:
    limiter = FixedWindowLimiter(limit=1, clock=Clock())
    assert limiter.allow("alpha").allowed
    assert not limiter.allow("alpha").allowed
    assert limiter.allow("beta").allowed


def test_zero_disables_the_limit() -> None:
    limiter = FixedWindowLimiter(limit=0, clock=Clock())
    assert all(limiter.allow("a").allowed for _ in range(1000))


def test_anonymous_traffic_shares_one_bucket() -> None:
    limiter = FixedWindowLimiter(limit=2, clock=Clock())
    assert limiter.allow(ANONYMOUS_BUCKET).allowed
    assert limiter.allow(ANONYMOUS_BUCKET).allowed
    assert not limiter.allow(ANONYMOUS_BUCKET).allowed


def test_old_windows_are_pruned() -> None:
    clock = Clock(1000.0)
    limiter = FixedWindowLimiter(limit=5, clock=clock)
    for i in range(50):
        limiter.allow(f"agent-{i}")
    clock.now += 120
    limiter.allow("fresh")
    assert limiter.tracked() == 1
