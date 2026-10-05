"""TC-7: the Python gate is green on the skeletons (AC-4, Python part)."""

import pytest

from .conftest import output, run

pytestmark = pytest.mark.rules


def test_check_python_is_green() -> None:
    result = run("make", "check-python")
    assert result.returncode == 0, output(result)


def test_check_python_runs_every_sub_check() -> None:
    dry = output(run("make", "-n", "check-python"))
    for expected in (
        "ruff check",
        "ruff format --check",
        "mypy",
        "lint-imports",
        "check_layout.py",
        "pytest",
    ):
        assert expected in dry, f"{expected!r} missing from: {dry}"
