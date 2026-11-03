"""Entrypoint for newsdock-extractor: wires adapters and runs the worker."""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from newsdock_config import load_settings, log_effective_config
from newsdock_config.health import write_heartbeat
from newsdock_db.config import Settings as DbSettings
from newsdock_db.engine import make_engine

from newsdock_extractor.adapters.db import SqlBodyRepo
from newsdock_extractor.adapters.fetch import FetchConfig, Fetcher
from newsdock_extractor.adapters.resolve import SystemResolver
from newsdock_extractor.adapters.wiring import worker_config
from newsdock_extractor.config import Settings
from newsdock_extractor.domain.loop import ExtractWorker, run
from newsdock_extractor.domain.picking import QueueRow
from newsdock_extractor.domain.schedule import HostScheduler

logger = logging.getLogger(__name__)


def now() -> datetime:
    return datetime.now(UTC)


async def serve(
    settings: Settings, *, should_stop: Callable[[], bool] = lambda: False
) -> None:
    """Build the worker from the settings; runs until `should_stop` (tests only)."""
    worker = ExtractWorker(
        SqlBodyRepo(make_engine(DbSettings())),
        Fetcher(
            FetchConfig.from_settings(settings),
            resolver=SystemResolver(),
            clock=now,
        ),
        HostScheduler[QueueRow](
            clock=time.monotonic,
            per_host_delay=settings.per_host_delay_seconds,
            max_crawl_delay=settings.max_crawl_delay_seconds,
        ),
        worker_config(settings),
        clock=now,
    )
    await run(
        worker,
        poll_interval=settings.poll_interval_seconds,
        backoff_base=settings.db_backoff_seconds,
        backoff_cap=settings.db_backoff_max_seconds,
        sleep=asyncio.sleep,
        beat=lambda: write_heartbeat(
            settings.heartbeat_file, settings.heartbeat_max_age_seconds
        ),
        should_stop=should_stop,
    )


def main() -> int:
    settings = load_settings(Settings)
    logging.basicConfig(level=settings.log_level)
    log_effective_config(logger, settings)
    logger.info("newsdock-extractor starting")
    asyncio.run(serve(settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
