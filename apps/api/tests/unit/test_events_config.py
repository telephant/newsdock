"""TC-23 (api part): the events-per-article cap is a setting with a default."""

import pytest
from newsdock_api.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("NEWSDOCK_CONFIG_FILE", "NEWSDOCK_EVENTS_PER_ARTICLE"):
        monkeypatch.delenv(name, raising=False)


def test_default_is_twenty() -> None:
    assert Settings().events_per_article == 20


def test_env_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSDOCK_EVENTS_PER_ARTICLE", "5")
    assert Settings().events_per_article == 5
