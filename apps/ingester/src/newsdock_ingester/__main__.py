"""Entrypoint for newsdock-ingester: wires adapters and runs the poll loop."""

import asyncio
import logging

from newsdock_config import load_settings, log_effective_config
from newsdock_db.config import Settings as DbSettings
from newsdock_db.engine import make_engine

from newsdock_ingester.adapters.gdelt import HttpGdeltSource
from newsdock_ingester.adapters.heartbeat import Heartbeat
from newsdock_ingester.adapters.kafka import KafkaRawPublisher
from newsdock_ingester.adapters.slots import SqlSlotRepo
from newsdock_ingester.config import Settings
from newsdock_ingester.domain.cycle import Ingester


async def run(settings: Settings) -> None:
    engine = make_engine(DbSettings())
    ingester = Ingester(
        HttpGdeltSource(
            settings.gdelt_base_url,
            timeout_seconds=settings.http_timeout_seconds,
            index_path=settings.gdelt_index_path,
        ),
        KafkaRawPublisher(
            settings.kafka_bootstrap_servers, topic=settings.kafka_topics_raw
        ),
        SqlSlotRepo(engine),
        base_url=settings.gdelt_base_url,
        max_attempts=settings.max_attempts,
    )
    heartbeat = Heartbeat(
        settings.heartbeat_file, max_age_seconds=settings.heartbeat_max_age_seconds
    )
    while True:
        await asyncio.to_thread(ingester.run_cycle)
        heartbeat.touch()
        await asyncio.sleep(settings.poll_interval_seconds)


def main() -> int:
    settings = load_settings(Settings)
    logging.basicConfig(level=settings.log_level)
    log_effective_config(logging.getLogger(__name__), settings)
    logging.getLogger(__name__).info(
        "newsdock-ingester starting (interval %ss)", settings.poll_interval_seconds
    )
    asyncio.run(run(settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
