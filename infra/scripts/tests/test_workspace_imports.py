"""TC-5: one environment can import every workspace package (AC-3, Python part)."""

import importlib
import sys

import pytest

PACKAGES = [
    "newsdock_core",
    "newsdock_core.gkg",
    "newsdock_core.urls",
    "newsdock_core.models",
    "newsdock_core.contracts",
    "newsdock_db",
    "newsdock_db.metadata",
    "newsdock_ingester",
    "newsdock_processor",
    "newsdock_sink",
    "newsdock_api",
    "newsdock_agent",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports(name: str) -> None:
    module = importlib.import_module(name)
    assert module.__name__ == name


def test_packages_come_from_one_environment() -> None:
    prefixes = {
        importlib.import_module(name).__file__ for name in PACKAGES if "." not in name
    }
    assert all(path is not None for path in prefixes)
    assert sys.prefix  # a single interpreter imported all of them
