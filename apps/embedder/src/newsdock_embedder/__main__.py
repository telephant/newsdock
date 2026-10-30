"""Entrypoint for newsdock-embedder: poll for unembedded articles and embed them."""

import logging
import time

from newsdock_config import load_settings, log_effective_config
from newsdock_config.health import write_heartbeat
from newsdock_db.config import Settings as DbSettings
from newsdock_db.engine import make_engine

from newsdock_embedder.adapters.db import SqlEmbedRepo
from newsdock_embedder.adapters.ollama import OllamaDocumentEmbedder
from newsdock_embedder.config import Settings
from newsdock_embedder.domain.loop import EmbedWorker, run
from newsdock_embedder.domain.selection import Backoff, SkipList

logger = logging.getLogger(__name__)


def main() -> int:
    settings = load_settings(Settings)
    logging.basicConfig(level=settings.log_level)
    log_effective_config(logger, settings)
    logger.info("newsdock-embedder starting")
    worker = EmbedWorker(
        SqlEmbedRepo(make_engine(DbSettings())),
        OllamaDocumentEmbedder(
            url=settings.embedding_ollama_url,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            prefix=settings.embedding_document_prefix,
            timeout=settings.ollama_timeout_seconds,
        ),
        model=settings.embedding_model,
        batch_size=settings.batch_size,
        skip=SkipList(
            max_failures=settings.skip_after_failures,
            max_entries=settings.skip_table_max_entries,
        ),
    )
    run(
        worker,
        poll_interval=settings.poll_interval_seconds,
        backoff=Backoff(
            base=settings.backoff_seconds, cap=settings.backoff_max_seconds
        ),
        sleep=time.sleep,
        beat=lambda: write_heartbeat(
            settings.heartbeat_file, settings.heartbeat_max_age_seconds
        ),
        should_stop=lambda: False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
