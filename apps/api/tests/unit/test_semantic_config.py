"""TC-17 (AC-15), API half: the semantic-search settings."""

from pathlib import Path

import pytest
from newsdock_api.config import Settings

ENV_NAMES = (
    "NEWSDOCK_CONFIG_FILE",
    "NEWSDOCK_SEMANTIC_CANDIDATES",
    "NEWSDOCK_EMBEDDING_MODEL",
    "NEWSDOCK_EMBEDDING_OLLAMA_URL",
    "OLLAMA_URL",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    path = tmp_path / "newsdock.yaml"
    path.write_text(text)
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", str(path))


def test_defaults() -> None:
    s = Settings()
    assert s.semantic_candidates == 50
    assert s.semantic_rrf_k == 60
    assert s.semantic_query_max_length == 500
    assert s.semantic_ef_search == 100
    assert s.semantic_ollama_timeout_seconds == 10.0
    assert s.embedding_model == "nomic-embed-text"
    assert s.embedding_dimension == 768
    assert s.embedding_query_prefix == "search_query: "


def test_shared_embedding_keys_come_from_common_and_the_section_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path,
        monkeypatch,
        "common:\n  embedding_model: other-model\n  embedding_query_prefix: 'q: '\n"
        "api:\n  semantic_candidates: 20\n",
    )
    s = Settings()
    assert (s.embedding_model, s.embedding_query_prefix) == ("other-model", "q: ")
    assert s.semantic_candidates == 20


def test_env_beats_the_file_and_ollama_url_has_a_short_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "api:\n  semantic_candidates: 20\n")
    monkeypatch.setenv("NEWSDOCK_SEMANTIC_CANDIDATES", "30")
    monkeypatch.setenv("OLLAMA_URL", "http://host.docker.internal:11434")
    s = Settings()
    assert s.semantic_candidates == 30
    assert s.embedding_ollama_url == "http://host.docker.internal:11434"
