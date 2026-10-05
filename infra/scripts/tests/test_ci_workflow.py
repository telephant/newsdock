"""TC-29, TC-30: the CI workflow checks and builds only what changed (AC-12, AC-13).

The path filters in `.github/workflows/ci.yml` are parsed and evaluated against
changed-file lists with the same glob semantics as dorny/paths-filter.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"
PYTHON_APPS = {"ingester", "processor", "sink", "api", "agent"}
BUILD_FILTERS = PYTHON_APPS | {"web", "migrate"}


def load() -> dict[Any, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text())
    assert isinstance(loaded, dict)
    return loaded


def triggers(workflow: dict[Any, Any]) -> dict[Any, Any]:
    # YAML 1.1 parses the key `on` as boolean True
    value = workflow.get("on", workflow.get(True))
    assert isinstance(value, dict)
    return value


def filters() -> dict[str, list[str]]:
    for step in load()["jobs"]["changes"]["steps"]:
        if str(step.get("uses", "")).startswith("dorny/paths-filter@"):
            parsed = yaml.safe_load(step["with"]["filters"])
            assert isinstance(parsed, dict)
            return {name: list(patterns) for name, patterns in parsed.items()}
    raise AssertionError("no dorny/paths-filter step in the changes job")


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(f"^{out}$")


def matched(files: list[str]) -> set[str]:
    result = set()
    for name, patterns in filters().items():
        regexes = [glob_to_regex(p) for p in patterns]
        if any(r.match(f) for r in regexes for f in files):
            result.add(name)
    return result


def build_matrix(files: list[str]) -> set[str]:
    return matched(files) & BUILD_FILTERS


def runs(files: list[str]) -> dict[str, bool]:
    hit = matched(files)
    return {
        "check-python": bool({"python", "tooling"} & hit),
        "check-web": bool({"web", "tooling"} & hit),
        "build": bool(hit & BUILD_FILTERS),
    }


def test_triggers_are_pull_request_and_push_to_main() -> None:
    on = triggers(load())
    assert "pull_request" in on
    assert on["push"]["branches"] == ["main"]


def test_web_only_change_skips_python_checks_and_builds_only_web() -> None:  # TC-29
    files = ["apps/web/src/app/page.tsx"]
    assert runs(files) == {"check-python": False, "check-web": True, "build": True}
    assert build_matrix(files) == {"web"}


def test_api_only_change_builds_only_the_api_image() -> None:  # TC-30
    files = ["apps/api/src/newsdock_api/config.py"]
    assert build_matrix(files) == {"api"}
    assert runs(files)["check-python"] and not runs(files)["check-web"]


@pytest.mark.parametrize(
    "path",
    [
        "packages/core/src/newsdock_core/gkg/__init__.py",
        "pyproject.toml",
        "uv.lock",
    ],
)
def test_shared_python_changes_rebuild_every_python_app(path: str) -> None:  # TC-30
    assert build_matrix([path]) >= PYTHON_APPS
    assert "web" not in build_matrix([path])


def test_db_and_migration_changes_build_the_migrate_image() -> None:
    assert "migrate" in build_matrix(["infra/migrations/versions/0001_baseline.py"])
    assert "migrate" in build_matrix(["packages/db/src/newsdock_db/engine.py"])
    assert "migrate" not in build_matrix(["apps/api/src/newsdock_api/config.py"])


def test_docs_only_change_builds_and_checks_nothing_heavy() -> None:
    assert runs(["docs/roadmap.md"]) == {
        "check-python": False,
        "check-web": False,
        "build": False,
    }


def test_tooling_changes_rerun_both_checks() -> None:
    for path in ("Makefile", ".github/workflows/ci.yml"):
        result = runs([path])
        assert result["check-python"] and result["check-web"]


def test_jobs_and_gate_are_wired() -> None:
    jobs = load()["jobs"]
    assert {"changes", "check-python", "check-web", "docs", "build", "ci-ok"} <= set(
        jobs
    )
    gate = jobs["ci-ok"]
    assert gate["if"] == "always()"
    assert {"changes", "check-python", "check-web", "docs", "build"} <= set(
        gate["needs"]
    )
    assert "fromJSON(needs.changes.outputs.apps)" in str(jobs["build"]["strategy"])
    assert "python" in jobs["check-python"]["if"]
    assert "web" in jobs["check-web"]["if"]


def test_every_action_is_pinned_by_tag() -> None:
    uses = [
        step["uses"]
        for job in load()["jobs"].values()
        for step in job["steps"]
        if "uses" in step
    ]
    assert uses
    for reference in uses:
        assert re.search(r"@v\d+(\.\d+\.\d+)?$", reference), (
            f"{reference} is not tag-pinned"
        )


def test_every_make_target_used_in_ci_exists() -> None:
    makefile = (REPO / "Makefile").read_text()
    defined = set(re.findall(r"^([a-zA-Z_-]+):", makefile, flags=re.MULTILINE))
    commands = [
        step["run"]
        for job in load()["jobs"].values()
        for step in job["steps"]
        if "run" in step
    ]
    used = {t for c in commands for t in re.findall(r"\bmake ([a-z-]+)", c)}
    assert used, "CI should call make targets"
    assert used <= defined, f"unknown make targets in CI: {used - defined}"


def test_setup_uv_is_pinned_to_an_exact_release() -> None:
    """setup-uv has no floating major tag: `@v10` fails the job setup."""
    refs = {
        step["uses"]
        for job in load()["jobs"].values()
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    }
    assert refs
    for reference in refs:
        assert re.search(r"@v\d+\.\d+\.\d+$", reference), reference


def test_python_job_does_not_run_rule_tests_that_need_pnpm() -> None:
    """The check-python job has no pnpm: web rule tests run via check-web or locally."""
    commands = " ".join(
        str(step.get("run", "")) for step in load()["jobs"]["check-python"]["steps"]
    )
    assert "make test-rules-python" in commands
    assert "make test-rules\n" not in commands + "\n"
    makefile = (REPO / "Makefile").read_text()
    assert 'pytest -m "rules and not web"' in makefile
