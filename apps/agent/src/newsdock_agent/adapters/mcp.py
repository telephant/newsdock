"""Synchronous wrapper over the async mcp client (AC-13: data only via MCP).

Sends `Authorization: Bearer <key>` on every request (T-01 spike). The mcp client
reports an HTTP 401 only as a generic error inside nested exception groups, so a
failed call is re-checked with one plain request to tell "key rejected" from
"API down".
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from newsdock_agent.domain.loop import SubmitFailed, Unauthorized

logger = logging.getLogger(__name__)


class ToolCallError(Exception):
    """A tool call returned is_error (e.g. not_found, payload_too_large)."""


class McpApiClient:
    def __init__(
        self,
        mcp_url: str,
        api_key: str | None = None,
        *,
        agent_name: str = "demo-financial",
        probe: Callable[[], int] | None = None,
    ) -> None:
        self._url = mcp_url
        self._api_key = api_key
        self._agent_name = agent_name  # only honoured by the API when auth is off
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

    def list_new_articles(self, limit: int) -> tuple[list[dict[str, object]], str]:
        page = self._call("list_new_articles", {"limit": limit})
        return page["articles"], page["next_cursor"]

    def ack_cursor(self, cursor: str) -> None:
        try:
            self._call("ack_cursor", {"cursor": cursor})
        except ToolCallError as exc:
            if "anonymous_agent" not in str(exc):
                raise
            # auth is off and no key is set: the API keeps no cursor for anonymous
            # callers, so each run re-reads the last hour (analyses upsert)
            logger.warning("anonymous agent: no server cursor kept (set an API key)")

    def submit_analysis(self, article_id: str, payload: dict[str, object]) -> None:
        try:
            self._call(
                "submit_analysis",
                {
                    "article_id": article_id,
                    "agent_name": self._agent_name,
                    "payload": payload,
                },
            )
        except ToolCallError as exc:
            raise SubmitFailed(article_id) from exc
