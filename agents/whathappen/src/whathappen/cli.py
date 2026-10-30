"""Wiring: settings to the real adapters, then the loop (or one cycle with --once)."""

import argparse
import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from whathappen.adapters.files import BaselineStore, DigestWriter
from whathappen.adapters.heartbeat import write_heartbeat
from whathappen.adapters.mcp import McpClient
from whathappen.adapters.summarize import OllamaSummariser
from whathappen.config import Settings
from whathappen.domain.digest import DigestCycle, DigestParams
from whathappen.domain.runner import run_cli

logger = logging.getLogger(__name__)


def build_cycle(settings: Settings) -> DigestCycle:
    key = settings.api_key.get_secret_value() if settings.api_key else None
    return DigestCycle(
        McpClient(settings.mcp_url, key),
        OllamaSummariser(
            settings.ollama_url,
            settings.model,
            timeout_seconds=settings.ollama_timeout_seconds,
            temperature=settings.ollama_temperature,
            max_chars=settings.summary_max_chars,
        ),
        DigestWriter(settings.output_path),
        BaselineStore(settings.state_path),
        DigestParams(
            page_size=settings.page_size,
            max_articles=settings.max_articles,
            skip_prefixes=settings.skip_prefixes,
            min_theme_count=settings.min_theme_count,
            max_themes=settings.max_themes,
            stories_per_theme=settings.stories_per_theme,
            prompt_titles=settings.prompt_titles,
            baseline_hours=settings.baseline_hours,
            baseline_min_entries=settings.baseline_min_entries,
            themes_kept=settings.baseline_themes_kept,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whathappen")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = parser.parse_args(argv)

    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    logger.info(
        "whathappen starting: platform %s, model %s, output %s",
        settings.mcp_url,
        settings.model,
        settings.output_path,
    )
    if settings.api_key is None:
        logger.warning(
            "no WHATHAPPEN_API_KEY set: only works while the platform runs with "
            "auth_required=false (and then no cursor is kept)"
        )
    return run_cli(
        build_cycle(settings),
        once=args.once,
        clock=lambda: datetime.now(UTC),
        sleep=time.sleep,
        interval_seconds=settings.interval_seconds,
        heartbeat=lambda: write_heartbeat(
            settings.heartbeat_file, settings.heartbeat_max_age_seconds
        ),
    )
