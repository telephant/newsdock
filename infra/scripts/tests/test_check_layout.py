"""TC-37…TC-41: check_layout.py enforces DR-1…DR-4 (AC-16)."""

import shutil
from pathlib import Path

import check_layout
import pytest

from .conftest import importlinter_toml, write

REPO = Path(__file__).resolve().parents[3]


def messages(root: Path, pending: dict[str, str] | None = None) -> list[str]:
    result = check_layout.check(root, pending={} if pending is None else pending)
    return [str(v) for v in result]


def test_valid_tree_has_no_violations(tree: Path) -> None:
    assert messages(tree) == []


def test_python_file_outside_src_or_tests_fails(tree: Path) -> None:  # TC-37
    write(tree / "apps" / "api" / "helper.py")
    found = messages(tree)
    assert any(m.startswith("DR-4") and "apps/api/helper.py" in m for m in found), found


def test_python_file_in_docs_fails(tree: Path) -> None:  # TC-37
    write(tree / "docs" / "snippet.py")
    assert any(m.startswith("DR-4") and "docs/snippet.py" in m for m in messages(tree))


def test_python_app_without_domain_or_adapters_fails(tree: Path) -> None:  # TC-37
    shutil.rmtree(tree / "apps" / "sink" / "src" / "newsdock_sink" / "domain")
    assert any(m.startswith("DR-4") and "domain" in m for m in messages(tree))


def test_missing_readme_fails(tree: Path) -> None:  # TC-38
    (tree / "apps" / "api" / "README.md").unlink()
    found = messages(tree)
    assert any(m.startswith("DR-3") and "apps/api/README.md" in m for m in found)


def test_missing_tests_dir_fails(tree: Path) -> None:  # TC-38
    shutil.rmtree(tree / "apps" / "agent" / "tests")
    assert any(m.startswith("DR-3") and "apps/agent/tests" in m for m in messages(tree))


def test_web_missing_package_json_fails(tree: Path) -> None:  # TC-38
    (tree / "apps" / "web" / "package.json").unlink()
    assert any(
        m.startswith("DR-3") and "apps/web/package.json" in m for m in messages(tree)
    )


def test_unlisted_top_level_entries_fail(tree: Path) -> None:  # TC-39
    write(tree / "scripts" / "run.sh")
    write(tree / "notes.txt")
    found = messages(tree)
    assert any(m.startswith("DR-1") and "scripts" in m for m in found)
    assert any(m.startswith("DR-1") and "notes.txt" in m for m in found)


def test_unknown_app_fails(tree: Path) -> None:  # TC-40
    write(tree / "apps" / "extra" / "README.md")
    assert any(m.startswith("DR-2") and "extra" in m for m in messages(tree))


def test_app_missing_from_import_contracts_fails(tree: Path) -> None:  # TC-40
    write(tree / "pyproject.toml", importlinter_toml(["ingester", "processor", "sink"]))
    found = messages(tree)
    assert any(m.startswith("DR-7") and "newsdock_api" in m for m in found), found
    assert any(m.startswith("DR-7") and "newsdock_agent" in m for m in found), found


def test_allowed_python_locations_and_ignored_dirs_pass(tree: Path) -> None:  # TC-41
    write(tree / "infra" / "scripts" / "tool.py")
    write(tree / "infra" / "migrations" / "env.py")
    for ignored in (".venv", "node_modules", "__pycache__", ".mypy_cache"):
        write(tree / ignored / "x.py")
        write(tree / "apps" / "api" / ignored / "x.py")
    assert messages(tree) == []


def test_pending_table_skips_only_listed_items(tree: Path) -> None:
    (tree / "apps" / "api" / "Dockerfile").unlink()
    assert any("apps/api/Dockerfile" in m for m in messages(tree))
    pending = {"Dockerfile": "T-08"}
    assert messages(tree, pending) == []


def test_main_prints_rule_and_path_and_exits_non_zero(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tree / "stray.txt")
    assert check_layout.main(tree) == 1
    assert "DR-1" in capsys.readouterr().out
    assert check_layout.main(build_clean(tree)) == 0


def build_clean(tree: Path) -> Path:
    (tree / "stray.txt").unlink()
    return tree


def test_real_repo_passes() -> None:
    found = [str(v) for v in check_layout.check(REPO)]
    assert found == [], found
