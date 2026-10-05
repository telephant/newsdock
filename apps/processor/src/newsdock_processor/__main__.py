"""Entrypoint for newsdock-processor: consume gkg.raw, route, loop forever."""

import logging
from pathlib import Path

from newsdock_processor.adapters.kafka import KafkaProcessorLoop
from newsdock_processor.config import Settings


def main() -> int:
    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    logging.getLogger(__name__).info("newsdock-processor starting")
    loop = KafkaProcessorLoop(settings)
    heartbeat = Path(settings.heartbeat_file)
    try:
        while True:
            loop.run_once(
                max_messages=settings.batch_size,
                timeout_seconds=settings.poll_timeout_seconds,
            )
            heartbeat.touch()
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
