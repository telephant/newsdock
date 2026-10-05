"""Smoke test: newsdock_core imports."""

import newsdock_core


def test_package_imports() -> None:
    assert newsdock_core.__name__ == "newsdock_core"
