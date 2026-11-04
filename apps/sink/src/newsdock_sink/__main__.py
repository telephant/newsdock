"""Entrypoint for newsdock-sink: batch writer loop + hourly retention."""

import logging
import time
from datetime import UTC, datetime

from newsdock_config import load_settings, log_effective_config
from newsdock_config.health import write_heartbeat
from newsdock_db.config import Settings as DbSettings
from newsdock_db.engine import make_engine

from newsdock_sink.adapters.db import SqlArticleWriter, SqlGdeltWriter
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
    engine = make_engine(DbSettings())
    writer = SqlArticleWriter(engine)
    gdelt_writer = SqlGdeltWriter(engine)
    loop = KafkaSinkLoop(settings, writer, gdelt_writer=gdelt_writer)
    last_retention = 0.0
    try:
        while True:
            loop.run_once()
            if time.monotonic() - last_retention > settings.retention_interval_seconds:
                try:
                    limit = cutoff(datetime.now(UTC), settings.retention_days)
                    deleted = writer.delete_ingested_before(limit)
                    events, mentions = gdelt_writer.delete_ingested_before(limit)
                    logger.info(
                        "retention: deleted %d articles, %d events, %d mentions",
                        deleted,
                        events,
                        mentions,
                    )
                    last_retention = time.monotonic()
                except DbUnavailable as exc:
                    logger.warning("retention skipped, db unavailable: %s", exc)
            write_heartbeat(settings.heartbeat_file, settings.heartbeat_max_age_seconds)
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
