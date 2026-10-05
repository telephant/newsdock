"""Helpers for rule tests: write a violation into the real tree, always remove it."""

import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def run(*cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd), cwd=ROOT, capture_output=True, text=True, check=False
    )


def output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


@contextmanager
def temp_module(directory: str, source: str, name: str = "") -> Iterator[Path]:
    """Create `<directory>/_rule_violation_<id>.py` (or `name` inside a temp dir)."""
    base = ROOT / directory
    tag = uuid.uuid4().hex[:8]
    if name:
        folder = base / f"_rule_tmp_{tag}"
        folder.mkdir()
        path = folder / name
    else:
        folder = None
        path = base / f"_rule_violation_{tag}.py"
    path.write_text(source)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)
        if folder is not None:
            for leftover in folder.glob("*"):
                leftover.unlink()
            folder.rmdir()


@pytest.fixture(scope="session", autouse=True)
def no_leftover_violations() -> Iterator[None]:
    yield
    leftovers = [
        p
        for pattern in ("_rule_violation_*.py", "_rule_tmp_*")
        for p in ROOT.glob(f"**/{pattern}")
        if ".venv" not in p.parts
    ]
    assert not leftovers, f"rule tests left files behind: {leftovers}"
