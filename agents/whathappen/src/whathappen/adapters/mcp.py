"""Synchronous wrapper over the async MCP client: the agent's only door to the data.

Sends `Authorization: Bearer <key>` on every request. The mcp client reports an HTTP
401 only as a generic error inside nested exception groups, so a failed call is
re-checked with one plain request to tell "key rejected" from "platform down".
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from whathappen.domain.errors import Unauthorized

logger = logging.getLogger(__name__)


class ToolCallError(Exception):
    """A tool call returned is_error (e.g. invalid_cursor, anonymous_agent)."""


class McpClient:
    def __init__(
        self,
        mcp_url: str,
        api_key: str | None = None,
        *,
        probe: Callable[[], int] | None = None,
    ) -> None:
        self._url = mcp_url
        self._api_key = api_key
        self._probe = probe or self._probe_status

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    def _probe_status(self) -> int:
        response = httpx.post(
            self._url,
            headers={
                **self._headers(),
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={},
            timeout=10,
        )
        return response.status_code

    def _raw_call(self, tool: str, arguments: dict[str, Any]) -> Any:
        async def go() -> tuple[bool, Any, Any]:
            http = httpx2.AsyncClient(headers=self._headers())
            transport = streamable_http_client(self._url, http_client=http)
            async with Client(transport) as client:
                result = await client.call_tool(tool, arguments)
                return result.is_error, result.content, result.structured_content

        # raised outside the client's task group, which would wrap it in a group
        is_error, content, structured = asyncio.run(go())
        if is_error:
            raise ToolCallError(f"tool {tool} failed: {content}")
        return structured

    def _call(self, tool: str, arguments: dict[str, Any]) -> Any:
        try:
            return self._raw_call(tool, arguments)
        except BaseExceptionGroup as group:
            try:
                status = self._probe()
            except httpx.HTTPError:
                raise group from None
            if status == 401:
                raise Unauthorized(self._url) from group
            raise

    def list_new_articles(
        self, limit: int, cursor: str | None = None
    ) -> tuple[list[dict[str, object]], str]:
        """One page. Without a cursor the server resumes this agent's acked position;
        an explicit cursor always wins, which is how the digest pages."""
        arguments: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            arguments["cursor"] = cursor
        page = self._call("list_new_articles", arguments)
        return page["articles"], page["next_cursor"]

    def ack_cursor(self, cursor: str) -> None:
        try:
            self._call("ack_cursor", {"cursor": cursor})
        except ToolCallError as exc:
            if "anonymous_agent" not in str(exc):
                raise
            # auth is off and no key is set: the server keeps no cursor for anonymous
            # callers, so each run re-reads the last hour
            logger.warning("anonymous agent: no server cursor kept (set an API key)")
