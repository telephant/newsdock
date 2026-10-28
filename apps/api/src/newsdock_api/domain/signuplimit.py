"""Sign-up attempt limiter (spec signup-rate-limit AC-1..AC-9, design C-30).

Two fixed windows, one per client address and one global. A window opens at the
first counted attempt and ends by time alone (refused attempts never extend it); once
`max` attempts are counted inside it, `attempt` refuses until it ends. A refusal
records nothing in either window. In memory, valid for one API worker (same
assumption as the login and agent limiters); the address table is pruned and has a
hard cap. A maximum of 0 switches that limit off. Thread-safe: sync routes run in a
thread pool, and a budget must not be overshot by parallel requests.
"""

import math
import threading
import time
from collections.abc import Callable

from newsdock_api.domain.ratelimit import Decision

UNKNOWN_ADDRESS = "unknown"  # every request without a peer address shares this key


class SignupLimiter:
    def __init__(
        self,
        max_per_address: int,
        max_total: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        *,
        max_entries: int = 10_000,
        prune_above: int = 1_000,
    ) -> None:
        self._max_address = max_per_address
        self._max_total = max_total
        self._window = window_seconds
        self._clock = clock
        self._max_entries = max_entries
        self._prune_above = prune_above
        self._lock = threading.Lock()
        # address -> (counted attempts, window start); dict order = recency
        self._per_address: dict[str, tuple[int, float]] = {}
        self._total: tuple[int, float] | None = None

    def attempt(self, address: str) -> Decision:
        """Count one sign-up attempt unless a window refuses it."""
        if self._max_address <= 0 and self._max_total <= 0:
            return Decision(True)
        with self._lock:
            now = self._clock()
            address_entry = self._live(self._per_address.get(address), now)
            total_entry = self._live(self._total, now)
            waits: list[int] = []
            if self._max_address > 0 and self._full(address_entry, self._max_address):
                waits.append(self._remaining(address_entry, now))
            if self._max_total > 0 and self._full(total_entry, self._max_total):
                waits.append(self._remaining(total_entry, now))
            if waits:
                return Decision(False, max(waits))
            if self._max_address > 0:
                self._per_address.pop(address, None)  # re-insert last: recency
                self._per_address[address] = self._bump(address_entry, now)
                if len(self._per_address) > self._prune_above:
                    self._prune(now)
            if self._max_total > 0:
                self._total = self._bump(total_entry, now)
            return Decision(True)

    def tracked(self) -> int:
        """Addresses currently held (for tests and the memory bound)."""
        with self._lock:
            return len(self._per_address)

    def _live(
        self, entry: tuple[int, float] | None, now: float
    ) -> tuple[int, float] | None:
        if entry is None or now - entry[1] >= self._window:
            return None  # no window, or it has ended
        return entry

    @staticmethod
    def _full(entry: tuple[int, float] | None, maximum: int) -> bool:
        return entry is not None and entry[0] >= maximum

    def _remaining(self, entry: tuple[int, float] | None, now: float) -> int:
        assert entry is not None
        return max(1, math.ceil(entry[1] + self._window - now))

    @staticmethod
    def _bump(entry: tuple[int, float] | None, now: float) -> tuple[int, float]:
        return (1, now) if entry is None else (entry[0] + 1, entry[1])

    def _prune(self, now: float) -> None:
        self._per_address = {
            k: v for k, v in self._per_address.items() if now - v[1] < self._window
        }
        while len(self._per_address) > self._max_entries:  # oldest first
            del self._per_address[next(iter(self._per_address))]
