"""Check the documentation rules behind AC-14 (DR-13).

Stdlib only. Usage: ``python infra/scripts/check_docs.py [ROOT]``.
- every app README has the sections Purpose, Entrypoint, Dependencies, Run/Test;
- every relative link in README.md, docs/**/*.md and app/package READMEs resolves.
Prints ``<file>: <problem>`` per finding and exits 1 when there is any.
"""

import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

APPS = ("ingester", "processor", "sink", "api", "agent", "web")
SECTIONS = ("Purpose", "Entrypoint", "Dependencies", "Run/Test")
SKIP_DIRS = {".git", ".venv", "node_modules", ".next", "__pycache__"}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"```.*?```", re.DOTALL)
INLINE = re.compile(r"`[^`\n]*`")


@dataclass(frozen=True)
class Problem:
    file: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.message}"


def markdown_files(root: Path) -> Iterator[Path]:
    candidates = [root / "README.md"]
    for pattern in ("docs/**/*.md", "apps/*/README.md", "packages/*/README.md"):
        candidates.extend(sorted(root.glob(pattern)))
    for path in candidates:
        if path.is_file() and not SKIP_DIRS.intersection(path.parts):
            yield path


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def check_sections(root: Path) -> list[Problem]:
    found = []
    for app in APPS:
        path = root / "apps" / app / "README.md"
        if not path.is_file():
            found.append(Problem(rel(root, path), "missing README.md"))
            continue
        headings = {
            line.lstrip("#").strip()
            for line in path.read_text().splitlines()
            if line.startswith("#")
        }
        for section in SECTIONS:
            if section not in headings:
                found.append(Problem(rel(root, path), f"missing section '{section}'"))
    return found


def check_links(root: Path) -> list[Problem]:
    found = []
    for path in markdown_files(root):
        text = INLINE.sub("", FENCE.sub("", path.read_text()))
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            file_part = target.split("#", 1)[0]
            if file_part and not (path.parent / file_part).exists():
                found.append(Problem(rel(root, path), f"broken link '{target}'"))
    return found


def check(root: Path) -> list[Problem]:
    return [*check_sections(root), *check_links(root)]


def main(root: Path | None = None) -> int:
    base = root if root is not None else Path(__file__).resolve().parents[2]
    problems = check(base)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
