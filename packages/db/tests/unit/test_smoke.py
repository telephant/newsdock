"""Smoke test: newsdock_db imports."""

import newsdock_db


def test_package_imports() -> None:
    assert newsdock_db.__name__ == "newsdock_db"
