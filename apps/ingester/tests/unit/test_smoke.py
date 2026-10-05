"""Smoke test: newsdock-ingester imports, has its layers, config floor holds."""

import importlib

import pytest
from newsdock_ingester.config import Settings


def test_poll_interval_never_below_900(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSDOCK_POLL_INTERVAL_SECONDS", "10")
    assert Settings().poll_interval_seconds == 900


@pytest.mark.parametrize("layer", ["domain", "adapters"])
def test_layer_packages_exist(layer: str) -> None:
    assert importlib.import_module(f"newsdock_ingester.{layer}")


def test_entrypoint_imports() -> None:
    assert importlib.import_module("newsdock_ingester.__main__")
