"""Summariser adapter (TC-16; AC-10): every failure becomes None, never an exception."""

import json
from collections.abc import Callable

import httpx
import pytest
from newsdock_agent.adapters.summarize import OllamaSummariser
from newsdock_agent.domain.prompt import theme_prompt

TITLES = ["ECB holds rates as inflation cools", "US CPI eases for third month"]


def summariser(
    handler: Callable[[httpx.Request], httpx.Response], *, max_chars: int = 300
) -> OllamaSummariser:
    return OllamaSummariser(
        "http://ollama.test",
        "qwen3:4b-instruct",
        timeout_seconds=7.0,
        temperature=0.0,
        max_chars=max_chars,
        transport=httpx.MockTransport(handler),
    )


def answer(content: str) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, json={"message": {"content": content}})


def test_request_is_a_plain_chat_call_with_the_theme_prompt() -> None:
    bodies: list[dict[str, object]] = []
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "Prices ease."}})

    assert summariser(handler).summarise("ECON INFLATION", TITLES) == "Prices ease."
    assert paths == ["/api/chat"]
    body = bodies[0]
    assert body["model"] == "qwen3:4b-instruct"
    assert body["stream"] is False
    assert "format" not in body  # prose, no JSON schema
    assert body["options"] == {"temperature": 0.0}
    assert body["messages"] == [
        {"role": "user", "content": theme_prompt("ECON INFLATION", TITLES)}
    ]


def test_timeout_is_applied_to_the_client() -> None:
    s = summariser(answer("x"))
    assert s._client.timeout.read == 7.0


def test_tc16_a_normal_sentence_is_returned_trimmed() -> None:
    assert summariser(answer("  Central banks hold rates.  \n")).summarise(
        "T", TITLES
    ) == ("Central banks hold rates.")


def test_tc16_multi_line_answers_with_markers_and_quotes_become_one_clean_line() -> (
    None
):
    raw = '\n\n- "Prices ease and rates hold."\nSecond line that is dropped.'
    assert summariser(answer(raw)).summarise("T", TITLES) == (
        "Prices ease and rates hold."
    )
    assert summariser(answer("1. Numbered line.\nmore")).summarise("T", TITLES) == (
        "Numbered line."
    )
    assert summariser(answer("“Curly quoted.”")).summarise("T", TITLES) == (
        "Curly quoted."
    )


def test_tc16_a_long_line_is_cut_within_the_limit() -> None:
    result = summariser(answer("word " * 200), max_chars=50).summarise("T", TITLES)
    assert result is not None
    assert len(result) <= 50 and result.endswith("…")


def test_tc16_a_think_block_is_dropped() -> None:
    raw = "<think>let me reason\nabout this</think>\nPrices ease."
    assert summariser(answer(raw)).summarise("T", TITLES) == "Prices ease."


@pytest.mark.parametrize("content", ["", "   \n\t", '""', "-", "<think>only</think>"])
def test_tc16_empty_answers_give_none(content: str) -> None:
    assert summariser(answer(content)).summarise("T", TITLES) is None


def test_tc16_a_response_without_a_message_gives_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    assert summariser(handler).summarise("T", TITLES) is None


@pytest.mark.parametrize("body", [[], "text", 7, None, {"message": "str"}])
def test_tc16_json_of_the_wrong_shape_gives_none(body: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    assert summariser(handler).summarise("T", TITLES) is None


def test_tc16_an_invalid_json_body_gives_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    assert summariser(handler).summarise("T", TITLES) is None


def test_tc16_http_errors_give_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    assert summariser(handler).summarise("T", TITLES) is None


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("ollama is down"),
        httpx.RemoteProtocolError("closed"),
    ],
)
def test_tc16_timeouts_and_connection_errors_give_none(error: Exception) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    assert summariser(handler).summarise("T", TITLES) is None
