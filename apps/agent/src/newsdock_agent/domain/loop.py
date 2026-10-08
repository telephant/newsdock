"""Agent loop (design.md F-2): list → pre-filter → score → submit → save cursor.

The cursor is saved only after the whole batch succeeded (R-2): a crash
mid-batch re-scores the batch, which is harmless because analyses upsert.
Pre-filter: themes must start with one of the prefixes (default ECON_ only,
spike decision 2026-10-05); empty themes are skipped by design.
"""

import logging
from typing import Protocol

from newsdock_agent.domain.score import Score

logger = logging.getLogger(__name__)


class SubmitFailed(Exception):
    """submit_analysis failed; keep the old cursor and retry next run."""


class McpPort(Protocol):
    def list_new_articles(
        self, cursor: str | None, limit: int
    ) -> tuple[list[dict[str, object]], str]: ...

    def submit_analysis(
        self, article_id: str, agent_name: str, payload: dict[str, object]
    ) -> None: ...


class ScorerPort(Protocol):
    def score(self, title: str) -> Score | None: ...


class CursorStore(Protocol):
    def load(self) -> str | None: ...

    def save(self, cursor: str) -> None: ...


class AgentLoop:
    def __init__(
        self,
        mcp: McpPort,
        scorer: ScorerPort,
        cursor_store: CursorStore,
        *,
        agent_name: str,
        theme_prefixes: tuple[str, ...],
        batch_limit: int,
    ) -> None:
        self._mcp = mcp
        self._scorer = scorer
        self._cursor_store = cursor_store
        self._agent_name = agent_name
        self._theme_prefixes = theme_prefixes
        self._batch_limit = batch_limit

    def _wanted(self, themes: list[str]) -> bool:
        return any(t.startswith(self._theme_prefixes) for t in themes)

    def run_once(self) -> int:
        """One batch; returns the number of analyses submitted."""
        cursor = self._cursor_store.load()
        articles, next_cursor = self._mcp.list_new_articles(cursor, self._batch_limit)
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
            self._mcp.submit_analysis(
                str(article["article_id"]), self._agent_name, score.model_dump()
            )
            submitted += 1
        # only now is the batch complete: advance the cursor (TC-32)
        self._cursor_store.save(next_cursor)
        logger.info(
            "batch done: %d of %d scored and submitted", submitted, len(articles)
        )
        return submitted
