"""TC-11 and TC-13: `make test APP=<name>` (AC-6, Python apps)."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PYTHON_APPS = ["ingester", "processor", "sink", "api", "agent"]


def run_make(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize("app", PYTHON_APPS)
def test_app_smoke_tests_pass(app: str) -> None:
    result = run_make("test", f"APP={app}")
    assert result.returncode == 0, result.stdout + result.stderr
    assert " passed" in result.stdout


def test_unknown_app_fails_with_message() -> None:
    result = run_make("test", "APP=nosuchapp")
    assert result.returncode != 0
    assert "unknown app" in (result.stdout + result.stderr)


def test_missing_app_argument_fails_with_usage() -> None:
    result = run_make("test")
    assert result.returncode != 0
    assert "usage" in (result.stdout + result.stderr).lower()


def test_app_without_tests_fails(tmp_path: Path) -> None:
    (tmp_path / "zz_notests" / "tests").mkdir(parents=True)
    (tmp_path / "zz_notests" / "tests" / "helpers.py").write_text("X = 1\n")
    result = run_make(
        "test", "APP=zz_notests", "PYTHON_APPS=zz_notests", f"APPS_DIR={tmp_path}"
    )
    assert result.returncode != 0
    assert "no tests ran for 'zz_notests'" in result.stderr
