"""Entrypoint for newsdock-processor: consume gkg.raw, route, loop forever."""

import logging

from newsdock_config import load_settings, log_effective_config
from newsdock_config.health import write_heartbeat

from newsdock_processor.adapters.kafka import KafkaProcessorLoop
from newsdock_processor.config import Settings


def main() -> int:
    settings = load_settings(Settings)
    logging.basicConfig(level=settings.log_level)
    log_effective_config(logging.getLogger(__name__), settings)
    logging.getLogger(__name__).info("newsdock-processor starting")
    loop = KafkaProcessorLoop(settings)
    try:
        while True:
            loop.run_once(
                max_messages=settings.batch_size,
                timeout_seconds=settings.poll_timeout_seconds,
            )
            write_heartbeat(settings.heartbeat_file, settings.heartbeat_max_age_seconds)
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
