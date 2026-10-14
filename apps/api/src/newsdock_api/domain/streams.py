"""Stream resources (design.md C-17): a per-agent cap and the wake hub.

`StreamLimiter` bounds open SSE connections per agent. `WakeHub` lets the single
NOTIFY listener (ADR-0018) wake every waiting stream; a generation counter means a
wake that lands while a stream is querying is never lost. Both are pure and in
memory, which is valid for one API worker.
"""

import asyncio
import threading


class StreamLimiter:
    def __init__(self, max_streams: int) -> None:
        self._max = max_streams
        self._open: dict[str, int] = {}
        self._lock = threading.Lock()

    def try_acquire(self, agent_id: str) -> bool:
        with self._lock:
            current = self._open.get(agent_id, 0)
            if current >= self._max:
                return False
            self._open[agent_id] = current + 1
            return True

    def release(self, agent_id: str) -> None:
        with self._lock:
            current = self._open.get(agent_id, 0)
            if current <= 1:
                self._open.pop(agent_id, None)
            else:
                self._open[agent_id] = current - 1

    def open_count(self, agent_id: str) -> int:
        with self._lock:
            return self._open.get(agent_id, 0)

    def tracked(self) -> int:
        with self._lock:
            return len(self._open)


class WakeHub:
    """Call `wake_all` from the event loop thread (the listener runs there)."""

    def __init__(self) -> None:
        self._generation = 0
        self._event = asyncio.Event()

    def generation(self) -> int:
        return self._generation

    def wake_all(self) -> None:
        self._generation += 1
        self._event.set()
        self._event = asyncio.Event()

    async def wait(self, since: int, timeout: float) -> bool:
        """True if woken after generation `since` (immediately if already so)."""
        if self._generation != since:
            return True
        event = self._event
        try:
            await asyncio.wait_for(event.wait(), timeout)
        except TimeoutError:
            return False
        return True
