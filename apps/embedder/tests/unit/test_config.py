"""TC-17 (AC-15), embedder half: settings from file and environment."""

from pathlib import Path

import pytest
from newsdock_embedder.config import Settings

ROOT = Path(__file__).resolve().parents[4]

ENV_NAMES = (
    "NEWSDOCK_CONFIG_FILE",
    "NEWSDOCK_LOG_LEVEL",
    "NEWSDOCK_BATCH_SIZE",
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
    assert s.embedding_model == "nomic-embed-text"
    assert s.embedding_dimension == 768
    assert s.embedding_document_prefix == "search_document: "
    assert s.batch_size == 32
    assert s.poll_interval_seconds == 10.0
    assert s.backoff_seconds == 5.0
    assert s.backoff_max_seconds == 60.0
    assert s.skip_after_failures == 3
    assert s.ollama_timeout_seconds == 60.0


def test_section_and_common_keys_reach_the_embedder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(
        tmp_path,
        monkeypatch,
        "common:\n  embedding_model: other-model\n  embedding_dimension: 384\n"
        "embedder:\n  batch_size: 8\n",
    )
    s = Settings()
    assert (s.embedding_model, s.embedding_dimension, s.batch_size) == (
        "other-model",
        384,
        8,
    )


def test_environment_beats_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "embedder:\n  batch_size: 8\n")
    monkeypatch.setenv("NEWSDOCK_BATCH_SIZE", "64")
    monkeypatch.setenv("OLLAMA_URL", "http://host.docker.internal:11434")
    s = Settings()
    assert s.batch_size == 64
    assert s.embedding_ollama_url == "http://host.docker.internal:11434"


def test_an_unknown_key_in_the_section_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, monkeypatch, "embedder:\n  batchsize: 3\n")
    with pytest.raises(Exception, match="batchsize"):
        Settings()
