"""Smoke test: newsdock-sink imports, has its layers and its entrypoint runs."""

import importlib

import pytest
from newsdock_sink.__main__ import main


def test_main_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    assert "newsdock-sink" in capsys.readouterr().out


@pytest.mark.parametrize("layer", ["domain", "adapters"])
def test_layer_packages_exist(layer: str) -> None:
    assert importlib.import_module(f"newsdock_sink.{layer}")
