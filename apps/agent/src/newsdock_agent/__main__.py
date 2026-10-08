"""Entrypoint for newsdock-agent: score new articles forever.

Any batch failure (Ollama down, API unreachable, submit error) leaves the
cursor unchanged; the next loop retries the same batch (design.md §5).
"""

import logging
import time

from newsdock_config import load_settings, log_effective_config
from newsdock_config.health import write_heartbeat

from newsdock_agent.adapters.cursor import FileCursorStore
from newsdock_agent.adapters.mcp import McpApiClient
from newsdock_agent.adapters.ollama import OllamaScorer
from newsdock_agent.config import Settings
from newsdock_agent.domain.loop import AgentLoop

logger = logging.getLogger(__name__)


def main() -> int:
    settings = load_settings(Settings)
    logging.basicConfig(level=settings.log_level)
    log_effective_config(logger, settings)
    logger.info("newsdock-agent starting (model %s)", settings.model)
    loop = AgentLoop(
        McpApiClient(settings.mcp_url),
        OllamaScorer(
            settings.ollama_url,
            settings.model,
            timeout_seconds=settings.ollama_timeout_seconds,
            temperature=settings.ollama_temperature,
        ),
        FileCursorStore(settings.cursor_file),
        agent_name=settings.agent_name,
        theme_prefixes=settings.prefixes,
        batch_limit=settings.batch_limit,
    )
    while True:
        try:
            loop.run_once()
        except Exception as exc:  # noqa: BLE001 — cursor unchanged, retry next loop
            logger.warning("batch failed, will retry: %s", exc)
        write_heartbeat(settings.heartbeat_file, settings.heartbeat_max_age_seconds)
        time.sleep(settings.loop_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
