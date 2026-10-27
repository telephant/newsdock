"""TC-32 (AC-13): per-account login failure limiter with a fake clock."""

from newsdock_api.domain.loginlimit import LoginLimiter


class Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make(
    max_failures: int = 3, window: int = 60, clock: Clock | None = None, **kw: int
) -> LoginLimiter:
    return LoginLimiter(max_failures, window, clock=clock or Clock(), **kw)


def test_allows_until_the_limit_is_reached() -> None:
    limiter = make(3)
    for _ in range(2):
        assert limiter.check("a@x.io").allowed
        limiter.record_failure("a@x.io")
    assert limiter.check("a@x.io").allowed  # two failures: one more try
    limiter.record_failure("a@x.io")
    blocked = limiter.check("a@x.io")
    assert not blocked.allowed


def test_retry_after_is_the_time_left_in_the_window() -> None:
    clock = Clock(1000.0)
    limiter = make(1, window=60, clock=clock)
    limiter.record_failure("a@x.io")
    clock.now = 1020.0
    assert limiter.check("a@x.io").retry_after == 40
    clock.now = 1059.5
    assert limiter.check("a@x.io").retry_after == 1  # never 0 while blocked


def test_window_expiry_resets() -> None:
    clock = Clock(1000.0)
    limiter = make(1, window=60, clock=clock)
    limiter.record_failure("a@x.io")
    assert not limiter.check("a@x.io").allowed
    clock.now = 1060.0
    assert limiter.check("a@x.io").allowed
    limiter.record_failure("a@x.io")  # a fresh window starts here
    assert not limiter.check("a@x.io").allowed


def test_success_clears_the_counter() -> None:
    limiter = make(2)
    limiter.record_failure("a@x.io")
    limiter.clear("a@x.io")
    limiter.record_failure("a@x.io")
    assert limiter.check("a@x.io").allowed  # only one failure counted


def test_accounts_are_independent() -> None:
    limiter = make(1)
    limiter.record_failure("a@x.io")
    assert not limiter.check("a@x.io").allowed
    assert limiter.check("b@x.io").allowed


def test_keys_are_case_and_space_normalized() -> None:
    limiter = make(1)
    limiter.record_failure("  A@X.io ")
    assert not limiter.check("a@x.io").allowed


def test_failures_while_blocked_do_not_extend_the_window() -> None:
    clock = Clock(1000.0)
    limiter = make(1, window=60, clock=clock)
    limiter.record_failure("a@x.io")
    clock.now = 1050.0
    # a blocked attempt is still counted but does not extend the window
    limiter.record_failure("a@x.io")
    clock.now = 1060.0
    assert limiter.check("a@x.io").allowed


def test_expired_entries_are_pruned() -> None:
    clock = Clock(1000.0)
    limiter = make(1, window=60, clock=clock, prune_above=5)
    for i in range(10):
        limiter.record_failure(f"u{i}@x.io")
    assert limiter.tracked() == 10
    clock.now = 1100.0
    limiter.record_failure("late@x.io")  # over the prune threshold: old windows go
    assert limiter.tracked() == 1


def test_memory_is_capped_even_when_nothing_has_expired() -> None:
    limiter = make(1, window=60, max_entries=50, prune_above=10)
    for i in range(500):
        limiter.record_failure(f"u{i}@x.io")
    assert limiter.tracked() <= 50
    assert not limiter.check("u499@x.io").allowed  # the newest entry survives


def test_zero_max_failures_disables_the_limit() -> None:
    limiter = make(0)
    for _ in range(20):
        limiter.record_failure("a@x.io")
    assert limiter.check("a@x.io").allowed
    assert limiter.tracked() == 0
