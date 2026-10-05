"""Entrypoint for newsdock-sink: batch writer loop + hourly retention."""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from newsdock_db.config import Settings as DbSettings
from newsdock_db.engine import make_engine

from newsdock_sink.adapters.db import SqlArticleWriter
from newsdock_sink.adapters.kafka import KafkaSinkLoop
from newsdock_sink.config import Settings
from newsdock_sink.domain.retention import cutoff
from newsdock_sink.domain.writer import DbUnavailable

logger = logging.getLogger(__name__)


def main() -> int:
    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    logger.info("newsdock-sink starting")
    writer = SqlArticleWriter(make_engine(DbSettings().database_url))
    loop = KafkaSinkLoop(settings, writer)
    heartbeat = Path(settings.heartbeat_file)
    last_retention = 0.0
    try:
        while True:
            loop.run_once()
            if time.monotonic() - last_retention > settings.retention_interval_seconds:
                try:
                    deleted = writer.delete_ingested_before(cutoff(datetime.now(UTC)))
                    logger.info("retention: deleted %d articles", deleted)
                    last_retention = time.monotonic()
                except DbUnavailable as exc:
                    logger.warning("retention skipped, db unavailable: %s", exc)
            heartbeat.touch()
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
