"""The hourly loop and the single-cycle mode (design.md F-41). No I/O of its own.

A failing cycle is logged and the loop goes on: nothing was acked, so the next cycle
reads the same window again. Time, sleeping and the heartbeat are passed in, so the
loop can be tested without waiting.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from whathappen.domain.errors import Unauthorized

logger = logging.getLogger(__name__)


class CycleRunner(Protocol):
    def run_once(self, now: datetime) -> object: ...


def run_guarded(cycle: CycleRunner, now: datetime) -> bool:
    """One cycle; any failure is logged (nothing was acked) and reported as False."""
    try:
        cycle.run_once(now)
    except Unauthorized:
        logger.error(
            "the platform rejected this agent's key (HTTP 401): "
            "check WHATHAPPEN_API_KEY (wrong, revoked or not set)"
        )
    except Exception as exc:  # noqa: BLE001 - no ack, the next cycle retries
        logger.warning("digest cycle failed, will retry: %s", exc)
    else:
        return True
    return False


def run_loop(
    cycle: CycleRunner,
    *,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    interval_seconds: int,
    heartbeat: Callable[[], None],
    max_cycles: int | None = None,
) -> None:
    heartbeat()  # healthy while the first cycle runs
    done = 0
    while True:
        run_guarded(cycle, clock())
        heartbeat()
        done += 1
        if max_cycles is not None and done >= max_cycles:
            return
        sleep(interval_seconds)


def run_cli(
    cycle: CycleRunner,
    *,
    once: bool,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    interval_seconds: int,
    heartbeat: Callable[[], None],
) -> int:
    if once:
        ok = run_guarded(cycle, clock())
        heartbeat()
        return 0 if ok else 1
    run_loop(
        cycle,
        clock=clock,
        sleep=sleep,
        interval_seconds=interval_seconds,
        heartbeat=heartbeat,
    )
    return 0
