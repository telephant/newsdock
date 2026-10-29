"""TC-20 (AC-11, AC-12, AC-17): the reset request limiter and the attempt limiter."""

from newsdock_api.domain.resetlimit import ResetAttemptLimiter, ResetRequestLimiter


class Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def requests(
    per_email: int = 3,
    per_address: int = 20,
    window: float = 3600,
    clock: Clock | None = None,
    **kw: int,
) -> ResetRequestLimiter:
    return ResetRequestLimiter(
        per_email, per_address, window, clock=clock or Clock(), **kw
    )


# ---- request limiter -------------------------------------------------------------
def test_an_email_is_allowed_up_to_its_limit_then_refused_with_a_wait() -> None:
    limiter = requests(per_email=3)
    assert [
        limiter.attempt("ada@example.com", "1.1.1.1").allowed for _ in range(3)
    ] == [True] * 3
    refused = limiter.attempt("ada@example.com", "1.1.1.1")
    assert not refused.allowed and refused.retry_after >= 1


def test_unknown_and_known_emails_are_counted_alike() -> None:
    # the limiter cannot tell them apart, which is the point (AC-11)
    limiter = requests(per_email=1)
    assert limiter.attempt("nobody@example.com", "1.1.1.1").allowed
    assert not limiter.attempt("nobody@example.com", "1.1.1.1").allowed


def test_the_email_key_ignores_case_and_surrounding_spaces() -> None:
    limiter = requests(per_email=1)
    assert limiter.attempt("Ada@Example.com ", "1.1.1.1").allowed
    assert not limiter.attempt("ada@example.com", "2.2.2.2").allowed


def test_other_emails_keep_their_own_budget() -> None:
    limiter = requests(per_email=1)
    assert limiter.attempt("a@example.com", "1.1.1.1").allowed
    assert limiter.attempt("b@example.com", "1.1.1.1").allowed


def test_an_address_is_limited_across_different_emails() -> None:
    limiter = requests(per_email=10, per_address=2)
    assert limiter.attempt("a@example.com", "1.1.1.1").allowed
    assert limiter.attempt("b@example.com", "1.1.1.1").allowed
    refused = limiter.attempt("c@example.com", "1.1.1.1")
    assert not refused.allowed and refused.retry_after >= 1
    assert limiter.attempt("c@example.com", "2.2.2.2").allowed  # another address


def test_a_refusal_by_the_address_does_not_use_up_the_email_budget() -> None:
    limiter = requests(per_email=1, per_address=1)
    assert limiter.attempt("x@example.com", "1.1.1.1").allowed
    assert not limiter.attempt("ada@example.com", "1.1.1.1").allowed  # address is full
    assert limiter.attempt(
        "ada@example.com", "2.2.2.2"
    ).allowed  # ada's own budget is intact


def test_budgets_return_when_the_window_passes() -> None:
    clock = Clock()
    limiter = requests(per_email=1, per_address=1, window=60, clock=clock)
    assert limiter.attempt("a@example.com", "1.1.1.1").allowed
    assert not limiter.attempt("a@example.com", "1.1.1.1").allowed
    clock.now += 61
    assert limiter.attempt("a@example.com", "1.1.1.1").allowed


def test_each_limit_can_be_switched_off_on_its_own() -> None:
    no_email_limit = requests(per_email=0, per_address=2)
    assert [
        no_email_limit.attempt("a@example.com", "1.1.1.1").allowed for _ in range(2)
    ] == [True, True]
    assert not no_email_limit.attempt(
        "a@example.com", "1.1.1.1"
    ).allowed  # address still applies
    no_address_limit = requests(per_email=1, per_address=0)
    assert no_address_limit.attempt("a@example.com", "1.1.1.1").allowed
    assert not no_address_limit.attempt(
        "a@example.com", "2.2.2.2"
    ).allowed  # email still applies
    off = requests(per_email=0, per_address=0)
    assert all(off.attempt("a@example.com", "1.1.1.1").allowed for _ in range(50))


def test_the_tables_stay_bounded() -> None:
    limiter = requests(per_email=1, per_address=1, max_entries=20, prune_above=10)
    for i in range(500):
        limiter.attempt(f"user{i}@example.com", f"10.0.{i // 250}.{i % 250}")
    assert limiter.tracked() <= 2 * 20


# ---- attempt limiter -------------------------------------------------------------
def test_reset_attempts_are_limited_per_address() -> None:
    limiter = ResetAttemptLimiter(3, 3600, clock=Clock())
    assert [limiter.attempt("1.1.1.1").allowed for _ in range(3)] == [True] * 3
    refused = limiter.attempt("1.1.1.1")
    assert not refused.allowed and refused.retry_after >= 1
    assert limiter.attempt("2.2.2.2").allowed


def test_a_refused_attempt_records_nothing_and_the_window_ends_on_time() -> None:
    clock = Clock()
    limiter = ResetAttemptLimiter(1, 60, clock=clock)
    assert limiter.attempt("1.1.1.1").allowed
    for _ in range(10):  # hammering while refused must not extend the window
        assert not limiter.attempt("1.1.1.1").allowed
    clock.now += 61
    assert limiter.attempt("1.1.1.1").allowed


def test_the_attempt_limit_zero_means_off() -> None:
    limiter = ResetAttemptLimiter(0, 3600, clock=Clock())
    assert all(limiter.attempt("1.1.1.1").allowed for _ in range(100))
