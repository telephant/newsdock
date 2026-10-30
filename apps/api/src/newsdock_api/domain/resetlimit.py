"""Limits for the password reset routes (spec AC-11, AC-12, AC-17; design C-45).

Built on `SignupLimiter` with its total limit switched off, so each limit is a bounded
per-key window with an injectable clock, a positive `Retry-After` on refusal, and
refusals that record nothing. In memory, valid for one API worker (the same assumption
as the login and sign-up limiters); the per-code attempt cap lives in the database.
"""

import time
from collections.abc import Callable

from newsdock_api.domain.ratelimit import Decision
from newsdock_api.domain.signuplimit import SignupLimiter


class ResetRequestLimiter:
    """Code requests: per client address first, then per normalized email.

    Known and unknown emails are counted alike, so a refusal reveals nothing. A request
    refused by the email window has already counted toward its address: it is traffic.
    """

    def __init__(
        self,
        max_per_email: int,
        max_per_address: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        *,
        max_entries: int = 10_000,
        prune_above: int = 1_000,
    ) -> None:
        self._by_address = SignupLimiter(
            max_per_address,
            0,
            window_seconds,
            clock,
            max_entries=max_entries,
            prune_above=prune_above,
        )
        self._by_email = SignupLimiter(
            max_per_email,
            0,
            window_seconds,
            clock,
            max_entries=max_entries,
            prune_above=prune_above,
        )

    def attempt(self, email: str, address: str) -> Decision:
        decision = self._by_address.attempt(address)
        if not decision.allowed:
            return decision  # nothing counted against the email
        return self._by_email.attempt(email.strip().lower())

    def tracked(self) -> int:
        return self._by_address.tracked() + self._by_email.tracked()


class ResetAttemptLimiter:
    """Reset attempts (the confirm route): per client address."""

    def __init__(
        self,
        max_per_address: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        *,
        max_entries: int = 10_000,
        prune_above: int = 1_000,
    ) -> None:
        self._limiter = SignupLimiter(
            max_per_address,
            0,
            window_seconds,
            clock,
            max_entries=max_entries,
            prune_above=prune_above,
        )

    def attempt(self, address: str) -> Decision:
        return self._limiter.attempt(address)

    def tracked(self) -> int:
        return self._limiter.tracked()
