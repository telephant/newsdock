"""Tree builders for layout and docs checks (fake repos in tmp_path)."""

from pathlib import Path

import pytest

PYTHON_APPS = ["ingester", "processor", "sink", "api", "agent"]
ROOT_FILES = [
    "Makefile",
    "uv.lock",
    ".python-version",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    "README.md",
    "CLAUDE.md",
]


def importlinter_toml(apps: list[str]) -> str:
    modules = ", ".join(f'"newsdock_{a}"' for a in apps)
    domains = ", ".join(f'"newsdock_{a}.domain"' for a in apps)
    return (
        '[project]\nname = "x"\n\n'
        "[[tool.importlinter.contracts]]\n"
        'name = "DR-7 apps are independent"\ntype = "independence"\n'
        f"modules = [{modules}]\n\n"
        "[[tool.importlinter.contracts]]\n"
        'name = "DR-6 domain is pure"\ntype = "forbidden"\n'
        f"source_modules = [{domains}]\nforbidden_modules = []\n"
    )


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def build_valid_tree(root: Path) -> Path:
    """A repo that satisfies DR-1…DR-4 and the contract-completeness rule."""
    for name in ROOT_FILES:
        write(root / name)
    write(root / "pyproject.toml", importlinter_toml(PYTHON_APPS))
    for app in PYTHON_APPS:
        base = root / "apps" / app
        for name in ("pyproject.toml", "Dockerfile", "README.md"):
            write(base / name)
        pkg = base / "src" / f"newsdock_{app}"
        for sub in ("domain", "adapters"):
            write(pkg / sub / "__init__.py")
        write(pkg / "__init__.py")
        write(base / "tests" / "unit" / "test_smoke.py")
    web = root / "apps" / "web"
    for name in ("package.json", "Dockerfile", "README.md"):
        write(web / name)
    write(web / "src" / "app" / "page.tsx")
    for shared in ("core", "db"):
        write(root / "packages" / shared / "pyproject.toml")
        write(root / "packages" / shared / "src" / f"newsdock_{shared}" / "__init__.py")
        write(root / "packages" / shared / "tests" / "unit" / "test_smoke.py")
    write(root / "infra" / "scripts" / "doctor.sh")
    write(root / "infra" / "scripts" / "check_layout.py")
    write(root / "infra" / "migrations" / "versions" / "0001_baseline.py")
    write(root / "docs" / "README.md")
    write(root / ".github" / "workflows" / "ci.yml")
    return root


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    return build_valid_tree(tmp_path)
