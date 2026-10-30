"""TC-18: the embedding client, the text recipe and vector validation."""

import json

import httpx
import pytest
from newsdock_embedding import (
    BadEmbedding,
    OllamaUnavailable,
    document_text,
    embed,
    query_text,
    validate,
)
from newsdock_embedding.testing import FakeOllama

URL = "http://ollama.test:11434"
MODEL = "nomic-embed-text"


def _embed(fake: FakeOllama, texts: list[str]) -> list[list[float]]:
    with httpx.Client(transport=fake.transport()) as client:
        return embed(texts, model=MODEL, url=URL, timeout=5.0, client=client)


def test_posts_model_and_input_list_and_parses_embeddings() -> None:
    fake = FakeOllama(dimension=8)
    vectors = _embed(fake, ["first title", "second title"])
    assert len(vectors) == 2 and all(len(v) == 8 for v in vectors)
    (request,) = fake.requests
    assert request.url.path == "/api/embed"
    assert json.loads(request.content) == {
        "model": MODEL,
        "input": ["first title", "second title"],
    }


def test_trailing_slash_in_url_is_fine() -> None:
    fake = FakeOllama(dimension=4)
    with httpx.Client(transport=fake.transport()) as client:
        embed(["x"], model=MODEL, url=URL + "/", timeout=5.0, client=client)
    assert fake.requests[0].url.path == "/api/embed"


def test_empty_input_sends_no_request() -> None:
    fake = FakeOllama()
    assert _embed(fake, []) == []
    assert fake.requests == []


def test_same_text_gives_same_vector_and_different_text_differs() -> None:
    fake = FakeOllama(dimension=16)
    a, b, c = _embed(fake, ["alpha", "alpha", "beta"])
    assert a == b and a != c


def test_prefixes_are_applied_by_the_text_helpers() -> None:
    assert document_text("A title", "search_document: ") == "search_document: A title"
    assert query_text("rates", "search_query: ") == "search_query: rates"
    assert document_text("A title", "") == "A title"
    assert query_text("  spaced  ", "") == "spaced"


@pytest.mark.parametrize(
    "mode", ["refuse", "timeout", "http500", "missing", "bad_json"]
)
def test_failures_become_ollama_unavailable(mode: str) -> None:
    fake = FakeOllama(mode=mode)
    with pytest.raises(OllamaUnavailable):
        _embed(fake, ["x"])


def test_missing_model_message_carries_the_body() -> None:
    fake = FakeOllama(mode="missing")
    with pytest.raises(OllamaUnavailable, match="not found"):
        _embed(fake, ["x"])


def test_error_body_in_the_message_is_truncated() -> None:
    fake = FakeOllama(mode="http500", body="x" * 5000)
    with pytest.raises(OllamaUnavailable) as caught:
        _embed(fake, ["x"])
    assert len(str(caught.value)) < 400


def test_count_mismatch_is_a_bad_embedding() -> None:
    fake = FakeOllama(mode="short_list")
    with pytest.raises(BadEmbedding, match="expected 2"):
        _embed(fake, ["one", "two"])


def test_validate_accepts_a_good_vector() -> None:
    validate([0.1, -0.2, 0.3], 3)


@pytest.mark.parametrize(
    "vector",
    [
        [0.1, 0.2],
        [0.1, 0.2, 0.3, 0.4],
        [0.1, float("nan"), 0.3],
        [0.1, float("inf"), 0.3],
    ],
)
def test_validate_rejects_wrong_length_and_non_finite(vector: list[float]) -> None:
    with pytest.raises(BadEmbedding):
        validate(vector, 3)
