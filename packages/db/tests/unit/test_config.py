"""TC-28: newsdock_db reads DATABASE_URL through its Settings (DR-9)."""

import pytest
from newsdock_db.config import Settings
from pydantic import ValidationError


def test_database_url_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5433/db")
    assert Settings().database_url == "postgresql+psycopg://u:p@localhost:5433/db"


def test_missing_database_url_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
