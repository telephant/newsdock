"""TC-15 support: the MCP client sends the key and names a 401 clearly."""

from typing import Any

import pytest
from mcp.shared.exceptions import MCPError
from newsdock_agent.adapters.mcp import McpApiClient, ToolCallError
from newsdock_agent.domain.loop import Unauthorized


def _group() -> BaseExceptionGroup[Any]:
    # what the mcp client raises on an HTTP 401 (T-01 spike): the status is lost
    return ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [
            ExceptionGroup(
                "inner", [MCPError(-32603, "Server returned an error response")]
            )
        ],
    )


def test_a_401_becomes_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    client = McpApiClient("http://api/mcp", api_key="ndk_x_y", probe=lambda: 401)

    def boom(self: McpApiClient, tool: str, arguments: dict[str, Any]) -> Any:
        raise _group()

    monkeypatch.setattr(McpApiClient, "_raw_call", boom)
    with pytest.raises(Unauthorized):
        client.list_new_articles(10)


def test_other_failures_pass_through(monkeypatch: pytest.MonkeyPatch) -> None:
    client = McpApiClient("http://api/mcp", api_key=None, probe=lambda: 200)

    def boom(self: McpApiClient, tool: str, arguments: dict[str, Any]) -> Any:
        raise _group()

    monkeypatch.setattr(McpApiClient, "_raw_call", boom)
    with pytest.raises(BaseExceptionGroup):
        client.list_new_articles(10)


def test_tc3_list_sends_the_cursor_only_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake(self: McpApiClient, tool: str, arguments: dict[str, Any]) -> Any:
        calls.append((tool, arguments))
        return {"articles": [{"article_id": "a"}], "next_cursor": "c2"}

    monkeypatch.setattr(McpApiClient, "_raw_call", fake)
    client = McpApiClient("http://api/mcp", api_key=None)
    assert client.list_new_articles(200) == ([{"article_id": "a"}], "c2")
    client.list_new_articles(200, cursor="c2")
    client.list_new_articles(200, cursor=None)
    assert calls == [
        ("list_new_articles", {"limit": 200}),
        ("list_new_articles", {"limit": 200, "cursor": "c2"}),
        ("list_new_articles", {"limit": 200}),
    ]


def test_list_has_no_cursor_argument_and_ack_calls_the_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake(self: McpApiClient, tool: str, arguments: dict[str, Any]) -> Any:
        calls.append((tool, arguments))
        return {"articles": [], "next_cursor": "c1", "cursor": "c1"}

    monkeypatch.setattr(McpApiClient, "_raw_call", fake)
    client = McpApiClient("http://api/mcp", api_key=None)
    assert client.list_new_articles(7) == ([], "c1")
    client.ack_cursor("c1")
    assert calls == [
        ("list_new_articles", {"limit": 7}),
        ("ack_cursor", {"cursor": "c1"}),
    ]


def test_anonymous_ack_is_tolerated_but_other_errors_are_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def anonymous(self: McpApiClient, tool: str, arguments: dict[str, Any]) -> Any:
        raise ToolCallError("tool ack_cursor failed: anonymous_agent: register")

    def invalid(self: McpApiClient, tool: str, arguments: dict[str, Any]) -> Any:
        raise ToolCallError("tool ack_cursor failed: invalid_cursor: x")

    client = McpApiClient("http://api/mcp")
    monkeypatch.setattr(McpApiClient, "_raw_call", anonymous)
    client.ack_cursor("c1")  # no raise
    monkeypatch.setattr(McpApiClient, "_raw_call", invalid)
    with pytest.raises(ToolCallError):
        client.ack_cursor("c1")
