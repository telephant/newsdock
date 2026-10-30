"""MCP client: key header, a 401 told apart from 'down', cursor only when given."""

from typing import Any

import pytest
from mcp.shared.exceptions import MCPError

from whathappen.adapters.mcp import McpClient, ToolCallError
from whathappen.domain.errors import Unauthorized


def _group() -> BaseExceptionGroup[Any]:
    # what the mcp client raises on an HTTP 401: the status itself is lost
    return ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [
            ExceptionGroup(
                "inner", [MCPError(-32603, "Server returned an error response")]
            )
        ],
    )


def _boom(self: McpClient, tool: str, arguments: dict[str, Any]) -> Any:
    raise _group()


def test_a_401_becomes_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    client = McpClient("http://api/mcp", api_key="ndk_x_y", probe=lambda: 401)
    monkeypatch.setattr(McpClient, "_raw_call", _boom)
    with pytest.raises(Unauthorized):
        client.list_new_articles(10)


def test_other_failures_pass_through(monkeypatch: pytest.MonkeyPatch) -> None:
    client = McpClient("http://api/mcp", api_key=None, probe=lambda: 200)
    monkeypatch.setattr(McpClient, "_raw_call", _boom)
    with pytest.raises(BaseExceptionGroup):
        client.list_new_articles(10)


def test_the_key_is_sent_as_a_bearer_header_and_omitted_without_one() -> None:
    assert McpClient("u", "ndk_a_b")._headers() == {"Authorization": "Bearer ndk_a_b"}
    assert McpClient("u", None)._headers() == {}


def test_list_sends_the_cursor_only_when_given(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake(self: McpClient, tool: str, arguments: dict[str, Any]) -> Any:
        calls.append((tool, arguments))
        return {"articles": [{"article_id": "a"}], "next_cursor": "c2"}

    monkeypatch.setattr(McpClient, "_raw_call", fake)
    client = McpClient("http://api/mcp", api_key=None)
    assert client.list_new_articles(200) == ([{"article_id": "a"}], "c2")
    client.list_new_articles(200, cursor="c2")
    client.list_new_articles(200, cursor=None)
    assert calls == [
        ("list_new_articles", {"limit": 200}),
        ("list_new_articles", {"limit": 200, "cursor": "c2"}),
        ("list_new_articles", {"limit": 200}),
    ]


def test_ack_calls_the_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake(self: McpClient, tool: str, arguments: dict[str, Any]) -> Any:
        calls.append((tool, arguments))
        return {"cursor": "c1"}

    monkeypatch.setattr(McpClient, "_raw_call", fake)
    McpClient("http://api/mcp").ack_cursor("c1")
    assert calls == [("ack_cursor", {"cursor": "c1"})]


def test_an_anonymous_ack_is_tolerated_but_other_ack_errors_are_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def anonymous(self: McpClient, tool: str, arguments: dict[str, Any]) -> Any:
        raise ToolCallError(
            "tool ack_cursor failed: anonymous_agent: register an agent"
        )

    def broken(self: McpClient, tool: str, arguments: dict[str, Any]) -> Any:
        raise ToolCallError("tool ack_cursor failed: invalid_cursor")

    client = McpClient("http://api/mcp")
    monkeypatch.setattr(McpClient, "_raw_call", anonymous)
    client.ack_cursor("c1")  # no raise
    monkeypatch.setattr(McpClient, "_raw_call", broken)
    with pytest.raises(ToolCallError):
        client.ack_cursor("c1")
