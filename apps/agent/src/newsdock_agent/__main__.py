"""Entrypoint for newsdock-agent: score new articles forever.

Any batch failure (Ollama down, API unreachable, submit error, rejected key)
means no ack: the server cursor stays and the next loop re-reads the same
batch (design.md §5, ADR-0017).
"""

import logging
import time

from newsdock_config import load_settings, log_effective_config
from newsdock_config.health import write_heartbeat

from newsdock_agent.adapters.mcp import McpApiClient
from newsdock_agent.adapters.ollama import OllamaScorer
from newsdock_agent.config import Settings
from newsdock_agent.domain.loop import AgentLoop, Unauthorized

logger = logging.getLogger(__name__)


def main() -> int:
    settings = load_settings(Settings)
    logging.basicConfig(level=settings.log_level)
    log_effective_config(logger, settings)
    logger.info("newsdock-agent starting (model %s)", settings.model)
    key = settings.api_key.get_secret_value() if settings.api_key else None
    if key is None:
        logger.warning(
            "no NEWSDOCK_AGENT_API_KEY set: only works while the API runs with "
            "auth_required=false"
        )
    loop = AgentLoop(
        McpApiClient(settings.mcp_url, key, agent_name=settings.agent_name),
        OllamaScorer(
            settings.ollama_url,
            settings.model,
            timeout_seconds=settings.ollama_timeout_seconds,
            temperature=settings.ollama_temperature,
        ),
        theme_prefixes=settings.prefixes,
        batch_limit=settings.batch_limit,
    )
    while True:
        try:
            loop.run_once()
        except Unauthorized:
            logger.error(
                "the API rejected this agent's key (HTTP 401): %s",
                "check NEWSDOCK_AGENT_API_KEY (wrong or revoked?)"
                if key
                else "NEWSDOCK_AGENT_API_KEY is not set",
            )
        except Exception as exc:  # noqa: BLE001 — no ack, retry next loop
            logger.warning("batch failed, will retry: %s", exc)
        write_heartbeat(settings.heartbeat_file, settings.heartbeat_max_age_seconds)
        time.sleep(settings.loop_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
