"""Synchronous wrapper over the async mcp client (AC-13: data only via MCP)."""

import asyncio
from typing import Any

from mcp import Client

from newsdock_agent.domain.loop import SubmitFailed


class ToolCallError(Exception):
    """A tool call returned is_error (e.g. not_found, payload_too_large)."""


class McpApiClient:
    def __init__(self, mcp_url: str) -> None:
        self._url = mcp_url

    def _call(self, tool: str, arguments: dict[str, Any]) -> Any:
        async def go() -> Any:
            async with Client(self._url) as client:
                result = await client.call_tool(tool, arguments)
                if result.is_error:
                    raise ToolCallError(f"tool {tool} failed: {result.content}")
                return result.structured_content

        return asyncio.run(go())

    def list_new_articles(
        self, cursor: str | None, limit: int
    ) -> tuple[list[dict[str, object]], str]:
        arguments: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            arguments["cursor"] = cursor
        page = self._call("list_new_articles", arguments)
        return page["articles"], page["next_cursor"]

    def submit_analysis(
        self, article_id: str, agent_name: str, payload: dict[str, object]
    ) -> None:
        try:
            self._call(
                "submit_analysis",
                {
                    "article_id": article_id,
                    "agent_name": agent_name,
                    "payload": payload,
                },
            )
        except ToolCallError as exc:
            raise SubmitFailed(article_id) from exc
