"""TC-6, TC-8, TC-12: the web project is part of setup, check and test (AC-3/4/6)."""

import pytest

from .conftest import ROOT, output, run

pytestmark = pytest.mark.rules

PACKAGE_JSON = ROOT / "apps" / "web" / "package.json"


def test_setup_web_installs_from_the_frozen_lockfile() -> None:  # TC-6
    dry = output(run("make", "-n", "setup-web"))
    assert "--frozen-lockfile" in dry
    result = run("make", "setup-web")
    assert result.returncode == 0, output(result)


def test_stale_lockfile_makes_setup_fail() -> None:  # TC-6
    original = PACKAGE_JSON.read_text()
    try:
        stale = original.replace(
            '"devDependencies": {', '"devDependencies": {\n    "left-pad": "1.3.0",', 1
        )
        assert stale != original
        PACKAGE_JSON.write_text(stale)
        result = run("make", "setup-web")
    finally:
        PACKAGE_JSON.write_text(original)
    assert result.returncode != 0


def test_check_web_runs_every_sub_check_and_is_green() -> None:  # TC-8
    dry = output(run("make", "-n", "check-web"))
    for script in ("lint", "format:check", "typecheck", "test"):
        assert f"run {script}" in dry, f"{script} missing from: {dry}"
    result = run("make", "check-web")
    assert result.returncode == 0, output(result)


def test_make_test_web_runs_at_least_one_test() -> None:  # TC-12
    result = run("make", "test", "APP=web")
    assert result.returncode == 0, output(result)
    assert "1 passed" in output(result) or "Tests  " in output(result)


def test_node_comes_from_pnpm_not_the_system() -> None:
    result = run("pnpm", "--dir", "apps/web", "exec", "node", "-v")
    assert result.stdout.strip().startswith("v24."), output(result)
