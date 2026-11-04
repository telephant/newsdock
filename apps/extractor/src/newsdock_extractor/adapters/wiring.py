"""Settings to the objects the worker is made of (the entry point only calls these)."""

from newsdock_extractor.config import Settings
from newsdock_extractor.domain.loop import WorkerConfig


def worker_config(settings: Settings) -> WorkerConfig:
    return WorkerConfig(
        batch_size=settings.batch_size,
        concurrency=settings.concurrency,
        retention_days=settings.retention_days,
        backfill_hours=settings.backfill_hours,
        min_chars=settings.min_chars,
        text_cap_chars=settings.text_cap_chars,
        passage_chars=settings.passage_chars,
        passage_max_chars=settings.passage_max_chars,
        max_attempts=settings.max_attempts,
        retry_backoff_minutes=settings.retry_backoff(),
        max_crawl_delay_seconds=settings.max_crawl_delay_seconds,
        robots_failure_minutes=settings.robots_failure_minutes,
    )
