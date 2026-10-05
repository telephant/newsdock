"""Entrypoint for newsdock-agent: score new articles forever.

Any batch failure (Ollama down, API unreachable, submit error) leaves the
cursor unchanged; the next loop retries the same batch (design.md §5).
"""

import logging
import time
from pathlib import Path

from newsdock_agent.adapters.cursor import FileCursorStore
from newsdock_agent.adapters.mcp import McpApiClient
from newsdock_agent.adapters.ollama import OllamaScorer
from newsdock_agent.config import Settings
from newsdock_agent.domain.loop import AgentLoop

logger = logging.getLogger(__name__)


def main() -> int:
    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    logger.info("newsdock-agent starting (model %s)", settings.model)
    loop = AgentLoop(
        McpApiClient(settings.mcp_url),
        OllamaScorer(settings.ollama_url, settings.model),
        FileCursorStore(settings.cursor_file),
        agent_name=settings.agent_name,
        theme_prefixes=settings.prefixes,
    )
    heartbeat = Path(settings.heartbeat_file)
    while True:
        try:
            loop.run_once()
        except Exception as exc:  # noqa: BLE001 — cursor unchanged, retry next loop
            logger.warning("batch failed, will retry: %s", exc)
        heartbeat.touch()
        time.sleep(settings.loop_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
