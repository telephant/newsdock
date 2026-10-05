"""TC-33…TC-35, TC-9: check_docs.py (AC-14) and its place in `make check`."""

import subprocess
from pathlib import Path

import check_docs
import pytest

from .conftest import PYTHON_APPS, write

REPO = Path(__file__).resolve().parents[3]
SECTIONS = ["Purpose", "Entrypoint", "Dependencies", "Run/Test"]


def readme(sections: list[str] | None = None, extra: str = "") -> str:
    parts = ["# app\n"] + [f"## {s}\n\ntext\n" for s in (sections or SECTIONS)]
    return "\n".join(parts) + extra


@pytest.fixture
def docs_tree(tmp_path: Path) -> Path:
    for app in [*PYTHON_APPS, "web"]:
        write(tmp_path / "apps" / app / "README.md", readme())
    write(tmp_path / "README.md", "# root\n\n[docs](docs/README.md)\n")
    write(tmp_path / "docs" / "README.md", "# docs\n\n[root](../README.md)\n")
    return tmp_path


def problems(root: Path) -> list[str]:
    return [str(p) for p in check_docs.check(root)]


def test_valid_tree_passes(docs_tree: Path) -> None:
    assert problems(docs_tree) == []


def test_real_repo_passes() -> None:  # TC-33
    assert problems(REPO) == []


def test_missing_section_names_file_and_section(docs_tree: Path) -> None:  # TC-34
    write(
        docs_tree / "apps" / "sink" / "README.md",
        readme(["Purpose", "Dependencies", "Run/Test"]),
    )
    found = problems(docs_tree)
    assert any("apps/sink/README.md" in m and "Entrypoint" in m for m in found), found


def test_missing_readme_is_reported(docs_tree: Path) -> None:  # TC-34
    (docs_tree / "apps" / "agent" / "README.md").unlink()
    assert any("apps/agent/README.md" in m for m in problems(docs_tree))


def test_broken_relative_link_names_file_and_link(docs_tree: Path) -> None:  # TC-35
    write(
        docs_tree / "docs" / "guide.md", "see [x](missing/file.md) and [ok](README.md)"
    )
    found = problems(docs_tree)
    assert any("docs/guide.md" in m and "missing/file.md" in m for m in found), found


def test_links_that_are_not_files_are_ignored(docs_tree: Path) -> None:
    text = (
        "[web](https://example.com) [mail](mailto:a@b.c) [anchor](#top)\n"
        "[file with anchor](README.md#section)\n"
        "```\n[not a link](nowhere.md)\n```\n"
        "`[inline](nowhere.md)`\n"
    )
    write(docs_tree / "docs" / "ok.md", text)
    assert problems(docs_tree) == []


def test_main_exit_codes(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert check_docs.main(docs_tree) == 0
    (docs_tree / "apps" / "web" / "README.md").unlink()
    assert check_docs.main(docs_tree) == 1
    assert "apps/web/README.md" in capsys.readouterr().out


def test_make_check_runs_docs_check() -> None:  # TC-9
    dry = subprocess.run(
        ["make", "-n", "check"], cwd=REPO, capture_output=True, text=True, check=False
    ).stdout
    for expected in ("check_docs.py", "ruff check", "mypy", "lint-imports", "run lint"):
        assert expected in dry, f"{expected!r} missing from make -n check"
