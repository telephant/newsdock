"""TC-28 (M1), TC-4/TC-7/TC-17 (externalize-config): newsdock_db Settings."""

from pathlib import Path

import pytest
from newsdock_config import ConfigError
from newsdock_db.config import Settings
from pydantic import ValidationError

URL = "postgresql+psycopg://u:p@localhost:5433/db"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NEWSDOCK_CONFIG_FILE",
        "DATABASE_URL",
        "NEWSDOCK_DATABASE_URL",
        "NEWSDOCK_DATABASE_POOL_SIZE",
    ):
        monkeypatch.delenv(name, raising=False)


def write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    path = tmp_path / "newsdock.yaml"
    path.write_text(text)
    monkeypatch.setenv("NEWSDOCK_CONFIG_FILE", str(path))


def test_database_url_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    assert Settings().database_url == URL


def test_missing_database_url_is_an_error() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_tc4_pool_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    s = Settings()
    assert (
        s.database_pool_size,
        s.database_max_overflow,
        s.database_pool_recycle_seconds,
        s.database_pool_pre_ping,
    ) == (5, 10, 1800, True)


def test_pool_values_come_from_common_in_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    write(tmp_path, monkeypatch, "common:\n  database:\n    pool_size: 3\n")
    assert Settings().database_pool_size == 3
    monkeypatch.setenv("NEWSDOCK_DATABASE_POOL_SIZE", "7")
    assert Settings().database_pool_size == 7  # env beats file


def test_tc7_database_url_in_the_file_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    write(tmp_path, monkeypatch, "common:\n  database_url: postgresql://x\n")
    with pytest.raises(ConfigError, match="database_url"):
        Settings()


def test_tc7_clean_file_still_gets_database_url_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    write(tmp_path, monkeypatch, "common:\n  log_level: INFO\n")
    assert Settings().database_url == URL
