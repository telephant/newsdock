"""Entrypoint for the what-happen digest: `python -m newsdock_agent.digest [--once]`.

Wires settings to the real adapters and runs one cycle at start and one every
`digest_interval_seconds`. A failing cycle is logged and the loop goes on: nothing is
acked, so the next cycle reads the same window again (design.md F-41, ADR-0028).
`--once` runs a single cycle and exits non-zero if it failed (`make digest-once`).
"""

import argparse
import logging
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from newsdock_config import load_settings, log_effective_config
from newsdock_config.health import write_heartbeat

from newsdock_agent.adapters.files import BaselineStore, DigestWriter
from newsdock_agent.adapters.mcp import McpApiClient
from newsdock_agent.adapters.summarize import OllamaSummariser
from newsdock_agent.config import Settings
from newsdock_agent.domain.digest import DigestCycle, DigestParams
from newsdock_agent.domain.loop import Unauthorized

logger = logging.getLogger(__name__)


class CycleRunner(Protocol):
    def run_once(self, now: datetime) -> object: ...


def _run_guarded(cycle: CycleRunner, now: datetime) -> bool:
    """One cycle; any failure is logged (nothing was acked) and reported as False."""
    try:
        cycle.run_once(now)
    except Unauthorized:
        logger.error(
            "the API rejected this agent's key (HTTP 401): "
            "check NEWSDOCK_AGENT_API_KEY (wrong, revoked or not set)"
        )
    except Exception as exc:  # noqa: BLE001 - no ack, the next cycle retries
        logger.warning("digest cycle failed, will retry: %s", exc)
    else:
        return True
    return False


def run_loop(
    cycle: CycleRunner,
    *,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    interval_seconds: int,
    heartbeat: Callable[[], None],
    max_cycles: int | None = None,
) -> None:
    heartbeat()  # healthy while the first cycle runs
    done = 0
    while True:
        _run_guarded(cycle, clock())
        heartbeat()
        done += 1
        if max_cycles is not None and done >= max_cycles:
            return
        sleep(interval_seconds)


def run_cli(
    cycle: CycleRunner,
    *,
    once: bool,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    interval_seconds: int,
    heartbeat: Callable[[], None],
) -> int:
    if once:
        ok = _run_guarded(cycle, clock())
        heartbeat()
        return 0 if ok else 1
    run_loop(
        cycle,
        clock=clock,
        sleep=sleep,
        interval_seconds=interval_seconds,
        heartbeat=heartbeat,
    )
    return 0


def build_cycle(settings: Settings) -> DigestCycle:
    key = settings.api_key.get_secret_value() if settings.api_key else None
    return DigestCycle(
        McpApiClient(settings.mcp_url, key, agent_name=settings.agent_name),
        OllamaSummariser(
            settings.ollama_url,
            settings.digest_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            temperature=settings.ollama_temperature,
            max_chars=settings.digest_summary_max_chars,
        ),
        DigestWriter(Path(settings.digest_dir)),
        BaselineStore(Path(settings.digest_state_file)),
        DigestParams(
            page_size=settings.batch_limit,
            max_articles=settings.digest_max_articles,
            skip_prefixes=settings.digest_skip_prefixes,
            min_theme_count=settings.digest_min_theme_count,
            max_themes=settings.digest_max_themes,
            stories_per_theme=settings.digest_stories_per_theme,
            prompt_titles=settings.digest_prompt_titles,
            baseline_hours=settings.digest_baseline_hours,
            baseline_min_entries=settings.digest_baseline_min_entries,
            themes_kept=settings.digest_baseline_themes_kept,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="newsdock_agent.digest")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = parser.parse_args(argv)

    settings = load_settings(Settings)
    logging.basicConfig(level=settings.log_level)
    log_effective_config(logger, settings)
    logger.info("newsdock-digest starting (model %s)", settings.digest_model)
    if settings.api_key is None:
        logger.warning(
            "no NEWSDOCK_AGENT_API_KEY set: only works while the API runs with "
            "auth_required=false (and then no cursor is kept)"
        )
    return run_cli(
        build_cycle(settings),
        once=args.once,
        clock=lambda: datetime.now(UTC),
        sleep=time.sleep,
        interval_seconds=settings.digest_interval_seconds,
        heartbeat=lambda: write_heartbeat(
            settings.heartbeat_file, settings.digest_heartbeat_max_age_seconds
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
