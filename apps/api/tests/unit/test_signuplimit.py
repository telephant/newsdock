"""TC-1 to TC-7 (AC-1, AC-2, AC-3, AC-4, AC-5, AC-8, AC-9): the sign-up limiter."""

import threading

from newsdock_api.domain.signuplimit import SignupLimiter


class Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make(
    per_address: int = 3,
    total: int = 0,
    window: float = 60,
    clock: Clock | None = None,
    **kw: int,
) -> SignupLimiter:
    return SignupLimiter(per_address, total, window, clock=clock or Clock(), **kw)


# TC-1: one address is limited (AC-1)
def test_an_address_is_allowed_up_to_its_limit_then_refused() -> None:
    limiter = make(per_address=3)
    assert [limiter.attempt("1.1.1.1").allowed for _ in range(3)] == [True] * 3
    refused = limiter.attempt("1.1.1.1")
    assert not refused.allowed
    assert refused.retry_after >= 1


# TC-2: other addresses are unaffected (AC-2)
def test_other_addresses_keep_their_own_budget() -> None:
    limiter = make(per_address=1)
    assert limiter.attempt("1.1.1.1").allowed
    assert not limiter.attempt("1.1.1.1").allowed
    assert limiter.attempt("2.2.2.2").allowed


# TC-3: the global cap holds (AC-3)
def test_the_global_cap_refuses_even_a_fresh_address() -> None:
    limiter = make(per_address=10, total=4)
    results = [limiter.attempt(f"10.0.0.{i}").allowed for i in range(5)]
    assert results == [True, True, True, True, False]
    assert limiter.attempt("10.0.0.99").retry_after >= 1


# TC-4: the window recovers (AC-4)
def test_the_window_recovers_and_the_count_restarts() -> None:
    clock = Clock(1000.0)
    limiter = make(per_address=3, window=60, clock=clock)
    for _ in range(3):
        assert limiter.attempt("a").allowed
    assert not limiter.attempt("a").allowed
    clock.now = 1060.0  # exactly one window later
    assert [limiter.attempt("a").allowed for _ in range(3)] == [True] * 3
    assert not limiter.attempt("a").allowed


def test_retry_after_is_the_time_left_and_never_zero() -> None:
    clock = Clock(1000.0)
    limiter = make(per_address=1, window=60, clock=clock)
    limiter.attempt("a")
    clock.now = 1020.0
    assert limiter.attempt("a").retry_after == 40
    clock.now = 1059.5
    assert limiter.attempt("a").retry_after == 1


# TC-5: refused attempts record nothing and never extend a window (AC-1, AC-3)
def test_a_global_refusal_does_not_burn_the_address_budget() -> None:
    limiter = make(per_address=5, total=2)
    assert limiter.attempt("a").allowed
    assert limiter.attempt("a").allowed
    assert not limiter.attempt("b").allowed  # the cap is full
    assert limiter.tracked() == 1  # only "a" is tracked; "b" left no trace


def test_an_address_refusal_does_not_burn_the_global_budget() -> None:
    limiter = make(per_address=1, total=3)
    assert limiter.attempt("a").allowed  # total 1
    assert not limiter.attempt("a").allowed  # refused: must not count globally
    assert limiter.attempt("b").allowed  # total 2
    assert limiter.attempt("c").allowed  # total 3
    assert not limiter.attempt("d").allowed  # now the cap is really full


def test_the_wait_is_the_larger_remaining_time_of_the_refusing_windows() -> None:
    clock = Clock(1000.0)
    limiter = make(per_address=1, total=2, window=60, clock=clock)
    assert limiter.attempt("x").allowed  # global window starts at 1000
    clock.now = 1030.0
    assert limiter.attempt("a").allowed  # a's window starts at 1030; cap now full
    clock.now = 1040.0
    refused = limiter.attempt("a")  # address: 50 s left, global: 20 s left
    assert not refused.allowed
    assert refused.retry_after == 50


def test_refused_attempts_do_not_extend_the_window() -> None:
    clock = Clock(1000.0)
    limiter = make(per_address=1, window=60, clock=clock)
    assert limiter.attempt("a").allowed
    clock.now = 1050.0
    assert not limiter.attempt("a").allowed  # refused, window still ends at 1060
    clock.now = 1060.0
    assert limiter.attempt("a").allowed


# TC-6: zero switches a limit off (AC-8, AC-5)
def test_both_limits_off_allows_everything_and_keeps_no_state() -> None:
    limiter = make(per_address=0, total=0)
    assert all(limiter.attempt("a").allowed for _ in range(100))
    assert limiter.tracked() == 0


def test_one_limit_off_leaves_the_other_working() -> None:
    only_total = make(per_address=0, total=2)
    results = [only_total.attempt(f"ip{i}").allowed for i in range(3)]
    assert results == [True, True, False]
    assert only_total.tracked() == 0  # addresses are not tracked without a limit
    only_address = make(per_address=1, total=0)
    assert only_address.attempt("a").allowed
    assert not only_address.attempt("a").allowed


# TC-7: the table is bounded (AC-9)
def test_the_address_table_never_exceeds_its_cap() -> None:
    limiter = make(per_address=1, window=3600, max_entries=5, prune_above=3)
    for i in range(50):
        assert limiter.attempt(f"ip{i}").allowed
        assert limiter.tracked() <= 5
    # the newest address is still limited correctly
    assert not limiter.attempt("ip49").allowed


# attempts are atomic: parallel requests cannot overshoot the budget
def test_parallel_attempts_cannot_overshoot_the_limit() -> None:
    limiter = make(per_address=10, total=0)
    allowed: list[bool] = []
    lock = threading.Lock()

    def hit() -> None:
        decision = limiter.attempt("same")
        with lock:
            allowed.append(decision.allowed)

    threads = [threading.Thread(target=hit) for _ in range(60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert allowed.count(True) == 10
