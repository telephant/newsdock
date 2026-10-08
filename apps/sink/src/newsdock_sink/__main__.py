"""Entrypoint for newsdock-sink: batch writer loop + hourly retention."""

import logging
import time
from datetime import UTC, datetime

from newsdock_config import load_settings, log_effective_config
from newsdock_config.health import write_heartbeat
from newsdock_db.config import Settings as DbSettings
from newsdock_db.engine import make_engine

from newsdock_sink.adapters.db import SqlArticleWriter
from newsdock_sink.adapters.kafka import KafkaSinkLoop
from newsdock_sink.config import Settings
from newsdock_sink.domain.retention import cutoff
from newsdock_sink.domain.writer import DbUnavailable

logger = logging.getLogger(__name__)


def main() -> int:
    settings = load_settings(Settings)
    logging.basicConfig(level=settings.log_level)
    log_effective_config(logger, settings)
    logger.info("newsdock-sink starting")
    writer = SqlArticleWriter(make_engine(DbSettings()))
    loop = KafkaSinkLoop(settings, writer)
    last_retention = 0.0
    try:
        while True:
            loop.run_once()
            if time.monotonic() - last_retention > settings.retention_interval_seconds:
                try:
                    deleted = writer.delete_ingested_before(
                        cutoff(datetime.now(UTC), settings.retention_days)
                    )
                    logger.info("retention: deleted %d articles", deleted)
                    last_retention = time.monotonic()
                except DbUnavailable as exc:
                    logger.warning("retention skipped, db unavailable: %s", exc)
            write_heartbeat(settings.heartbeat_file, settings.heartbeat_max_age_seconds)
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
