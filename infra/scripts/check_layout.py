"""Check the repository layout rules DR-1…DR-4 (spec §6, ADR-0006).

Stdlib only. Usage: ``python infra/scripts/check_layout.py [ROOT]``. Prints one line
per violation as ``DR-n <message>: <path>`` and exits 1 when any is found.

PENDING_UNTIL lists required skeleton items that later foundation tasks create. It is
empty now that every skeleton item exists; keep the mechanism for future additions.
"""

import sys
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT_DIRS = {"apps", "packages", "infra", "docs", ".github"}
ROOT_FILES = {
    "Makefile",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    "README.md",
    "CLAUDE.md",
}
IGNORED = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".import_linter_cache",
    ".next",
    ".DS_Store",
}
PYTHON_APPS = ("ingester", "processor", "sink", "api", "agent")
APP_NAMES = {*PYTHON_APPS, "web"}
PYTHON_APP_FILES = ("pyproject.toml", "Dockerfile", "README.md")
WEB_FILES = ("package.json", "Dockerfile", "README.md")
PYTHON_OUTSIDE_ALLOWED = ("infra/scripts/", "infra/migrations/")

# required item (path relative to its app) -> task that creates it
PENDING_UNTIL: dict[str, str] = {}


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    path: str

    def __str__(self) -> str:
        return f"{self.rule} {self.message}: {self.path}"


def walk(base: Path) -> Iterator[Path]:
    """Yield files below ``base``, skipping ignored directories."""
    for entry in sorted(base.iterdir()):
        if entry.name in IGNORED:
            continue
        if entry.is_dir():
            yield from walk(entry)
        else:
            yield entry


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def check_root(root: Path) -> list[Violation]:
    found = []
    for entry in sorted(root.iterdir()):
        if entry.name in IGNORED:
            continue
        allowed = ROOT_DIRS if entry.is_dir() else ROOT_FILES
        if entry.name not in allowed:
            found.append(Violation("DR-1", "unexpected top-level entry", entry.name))
    return found


def check_app_skeleton(
    root: Path, app: Path, pending: dict[str, str]
) -> list[Violation]:
    if app.name == "web":
        required = [*WEB_FILES, "src"]
    else:
        required = [*PYTHON_APP_FILES, f"src/newsdock_{app.name}", "tests"]
    found = [
        Violation("DR-3", "missing", rel(root, app / item))
        for item in required
        if item not in pending and not (app / item).exists()
    ]
    if app.name != "web":
        package = app / "src" / f"newsdock_{app.name}"
        for layer in ("domain", "adapters"):
            if package.is_dir() and not (package / layer).is_dir():
                path = rel(root, package / layer)
                found.append(Violation("DR-4", f"missing {layer}/ layer", path))
    return found


def check_python_files(root: Path, base: Path, package: str) -> list[Violation]:
    """Python in an app or package only under src/<package>/ or tests/ (DR-4)."""
    allowed = (base / "src" / package, base / "tests")
    return [
        Violation("DR-4", f"Python file outside src/{package}/ or tests/", rel(root, p))
        for p in walk(base)
        if p.suffix == ".py" and not any(p.is_relative_to(a) for a in allowed)
    ]


def check_apps(root: Path, pending: dict[str, str]) -> list[Violation]:
    found: list[Violation] = []
    apps = root / "apps"
    if not apps.is_dir():
        return found
    for entry in sorted(apps.iterdir()):
        if entry.name in IGNORED:
            continue
        if not entry.is_dir() or entry.name not in APP_NAMES:
            found.append(Violation("DR-2", "unknown app", rel(root, entry)))
            continue
        found.extend(check_app_skeleton(root, entry, pending))
        found.extend(check_python_files(root, entry, f"newsdock_{entry.name}"))
    return found


def check_packages(root: Path) -> list[Violation]:
    found: list[Violation] = []
    packages = root / "packages"
    if packages.is_dir():
        for pkg in sorted(packages.iterdir()):
            if pkg.is_dir() and pkg.name not in IGNORED:
                found.extend(check_python_files(root, pkg, f"newsdock_{pkg.name}"))
    return found


def check_python_elsewhere(root: Path) -> list[Violation]:
    """Outside apps and packages, Python is allowed only in infra/scripts|migrations."""
    found = []
    for path in walk(root):
        where = rel(root, path)
        if path.suffix != ".py" or "/" not in where:
            continue  # root-level files are reported by DR-1
        if where.split("/")[0] in {"apps", "packages"}:
            continue
        if not where.startswith(PYTHON_OUTSIDE_ALLOWED):
            found.append(Violation("DR-4", "Python file in a non-Python place", where))
    return found


def contract_modules(root: Path) -> tuple[set[str], set[str]]:
    """(modules of independence contracts, source modules of forbidden contracts)."""
    config = root / "pyproject.toml"
    if not config.is_file():
        return set(), set()
    data = tomllib.loads(config.read_text())
    contracts = data.get("tool", {}).get("importlinter", {}).get("contracts", [])
    independent: set[str] = set()
    sources: set[str] = set()
    for contract in contracts:
        independent.update(contract.get("modules", []))
        sources.update(contract.get("source_modules", []))
    return independent, sources


def check_contracts(root: Path) -> list[Violation]:
    """Every Python app must be in the import-linter contracts (keeps AC-7 honest)."""
    independent, sources = contract_modules(root)
    apps = root / "apps"
    names = (
        sorted(p.name for p in apps.iterdir() if p.is_dir() and p.name in PYTHON_APPS)
        if apps.is_dir()
        else []
    )
    found = []
    for name in names:
        package = f"newsdock_{name}"
        if package not in independent:
            message = f"{package} missing from the independence contract"
            found.append(Violation("DR-7", message, "pyproject.toml"))
        if f"{package}.domain" not in sources:
            message = f"{package}.domain missing from the domain contract"
            found.append(Violation("DR-6", message, "pyproject.toml"))
    return found


def check(root: Path, pending: dict[str, str] | None = None) -> list[Violation]:
    pending = PENDING_UNTIL if pending is None else pending
    return [
        *check_root(root),
        *check_apps(root, pending),
        *check_packages(root),
        *check_python_elsewhere(root),
        *check_contracts(root),
    ]


def main(root: Path | None = None) -> int:
    base = root if root is not None else Path(__file__).resolve().parents[2]
    violations = check(base)
    for violation in violations:
        print(violation)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
