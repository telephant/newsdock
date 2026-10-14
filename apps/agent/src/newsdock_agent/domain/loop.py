"""Agent loop (design.md F-2): list → pre-filter → score → submit → ack cursor.

The position lives on the server (M2 agent-platform, ADR-0017): the loop calls
`ack_cursor` only after the whole batch succeeded, so a crash mid-batch re-reads
and re-scores the batch, which is harmless because analyses upsert.
Pre-filter: themes must start with one of the prefixes (default ECON_ only,
spike decision 2026-10-05); empty themes are skipped by design.
"""

import logging
from typing import Protocol

from newsdock_agent.domain.score import Score

logger = logging.getLogger(__name__)


class SubmitFailed(Exception):
    """submit_analysis failed; keep the old cursor and retry next run."""


class Unauthorized(Exception):
    """The API rejected the agent's key (HTTP 401): wrong, revoked or missing."""


class McpPort(Protocol):
    def list_new_articles(self, limit: int) -> tuple[list[dict[str, object]], str]: ...

    def ack_cursor(self, cursor: str) -> None: ...

    def submit_analysis(self, article_id: str, payload: dict[str, object]) -> None: ...


class ScorerPort(Protocol):
    def score(self, title: str) -> Score | None: ...


class AgentLoop:
    def __init__(
        self,
        mcp: McpPort,
        scorer: ScorerPort,
        *,
        theme_prefixes: tuple[str, ...],
        batch_limit: int,
    ) -> None:
        self._mcp = mcp
        self._scorer = scorer
        self._theme_prefixes = theme_prefixes
        self._batch_limit = batch_limit

    def _wanted(self, themes: list[str]) -> bool:
        return any(t.startswith(self._theme_prefixes) for t in themes)

    def run_once(self) -> int:
        """One batch; returns the number of analyses submitted."""
        articles, next_cursor = self._mcp.list_new_articles(self._batch_limit)
        submitted = 0
        for article in articles:
            themes = article.get("themes") or []
            if not isinstance(themes, list) or not self._wanted(
                [str(t) for t in themes]
            ):
                continue
            title = str(article.get("title", ""))
            score = self._scorer.score(title)
            if score is None:  # malformed model output: log and skip (TC-29)
                logger.warning("unscorable article %s", article.get("article_id"))
                continue
            self._mcp.submit_analysis(str(article["article_id"]), score.model_dump())
            submitted += 1
        # only now is the batch complete: acknowledge it (TC-15)
        self._mcp.ack_cursor(next_cursor)
        logger.info(
            "batch done: %d of %d scored and submitted", submitted, len(articles)
        )
        return submitted
