"""Wiring: settings to the real adapters, then the loop (or one cycle with --once)."""

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from whathappen.adapters import cleanup
from whathappen.adapters.files import DigestWriter
from whathappen.adapters.heartbeat import write_heartbeat
from whathappen.adapters.mcp import McpClient
from whathappen.adapters.summarize import OllamaSummariser
from whathappen.config import Settings
from whathappen.domain.digest import DigestCycle, DigestParams
from whathappen.domain.grouping import LexicalGrouper
from whathappen.domain.runner import run_cli
from whathappen.domain.titles import MatchParams

logger = logging.getLogger(__name__)


def build_cycle(settings: Settings) -> DigestCycle:
    key = settings.api_key.get_secret_value() if settings.api_key else None
    return DigestCycle(
        McpClient(settings.mcp_url, key),
        LexicalGrouper(
            MatchParams(
                overlap=settings.match_overlap,
                jaccard=settings.match_jaccard,
                min_shared=settings.match_min_shared,
            ),
            timedelta(hours=settings.group_window_hours),
        ),
        OllamaSummariser(
            settings.ollama_url,
            settings.model,
            timeout_seconds=settings.ollama_timeout_seconds,
            temperature=settings.ollama_temperature,
            max_chars=settings.summary_max_chars,
        ),
        DigestWriter(settings.output_path),
        DigestParams(
            page_size=settings.page_size,
            max_articles=settings.max_articles,
            min_group_sources=settings.min_group_sources,
            top_stories=settings.top_stories,
            max_sections=settings.max_sections,
            groups_per_section=settings.groups_per_section,
            also_per_group=settings.also_per_group,
            section_min_hits=settings.section_min_hits,
            tone_divisor=settings.tone_divisor,
            labels=settings.section_label_map,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whathappen")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    commands = parser.add_subparsers(dest="command")
    clean = commands.add_parser(
        "clean-old", help="delete the old theme digest's output files (one time)"
    )
    clean.add_argument(
        "--dry-run", action="store_true", help="list the files, delete nothing"
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if args.command == "clean-old":
        return cleanup.run(settings.output_path, dry_run=args.dry_run, out=sys.stdout)
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
