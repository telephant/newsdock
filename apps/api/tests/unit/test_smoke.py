"""Smoke test: newsdock-api imports and has its layers."""

import importlib

import pytest


@pytest.mark.parametrize("layer", ["domain", "adapters"])
def test_layer_packages_exist(layer: str) -> None:
    assert importlib.import_module(f"newsdock_api.{layer}")


def test_entrypoint_imports() -> None:
    assert importlib.import_module("newsdock_api.__main__")
