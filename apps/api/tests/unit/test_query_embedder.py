"""The API's query embedder: prefix, dimension check and error mapping (AC-10)."""

import json

import httpx
import pytest
from newsdock_api.adapters.query_embedder import OllamaQueryEmbedder
from newsdock_api.domain.semantic import EmbeddingUnavailable
from newsdock_embedding.testing import FakeOllama

URL = "http://ollama.test:11434"
PREFIX = "search_query: "


def make(fake: FakeOllama, dimension: int = 16) -> OllamaQueryEmbedder:
    return OllamaQueryEmbedder(
        url=URL,
        model="nomic-embed-text",
        dimension=dimension,
        prefix=PREFIX,
        timeout=5.0,
        client=httpx.Client(transport=fake.transport()),
    )


def test_the_query_goes_out_with_the_query_prefix() -> None:
    fake = FakeOllama(dimension=16)
    vector = make(fake).embed_query("interest rate hike")
    assert len(vector) == 16
    assert json.loads(fake.requests[0].content) == {
        "model": "nomic-embed-text",
        "input": [PREFIX + "interest rate hike"],
    }


@pytest.mark.parametrize(
    "mode", ["refuse", "timeout", "http500", "missing", "bad_json"]
)
def test_ollama_failures_become_embedding_unavailable(mode: str) -> None:
    with pytest.raises(EmbeddingUnavailable):
        make(FakeOllama(mode=mode)).embed_query("x")


@pytest.mark.parametrize("mode", ["short_vector", "nan", "short_list"])
def test_a_bad_vector_is_embedding_unavailable(mode: str) -> None:
    with pytest.raises(EmbeddingUnavailable):
        make(FakeOllama(dimension=16, mode=mode)).embed_query("x")


def test_a_vector_of_the_wrong_dimension_is_embedding_unavailable() -> None:
    with pytest.raises(EmbeddingUnavailable, match="dimensions"):
        make(FakeOllama(dimension=8), dimension=16).embed_query("x")
