"""Check the config file and that no tunable literal creeps back into code (AC-11).

Usage: ``python infra/scripts/check_config.py [ROOT]``. One line per violation as
``CFG <message>: <path>``; exits 1 when any is found. Rules:

1. ``infra/config/newsdock.yaml`` parses; every ``common`` key is a setting of at
   least one service (or the web app); every service-section key is a setting of that
   service; no secret-looking key anywhere.
2. Every value in the file equals the code default (the file documents defaults, so
   an empty file behaves the same).
3. No topic-name string literal or listed constant name in app/package source outside
   ``config.py`` (docstrings and tests exempt); same for the web constants.
"""

import ast
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from newsdock_agent.config import Settings as AgentSettings
from newsdock_api.config import Settings as ApiSettings
from newsdock_config.secrets import is_secret_name
from newsdock_config.source import flatten
from newsdock_db.config import Settings as DbSettings
from newsdock_ingester.config import Settings as IngesterSettings
from newsdock_processor.config import Settings as ProcessorSettings
from newsdock_sink.config import Settings as SinkSettings
from pydantic_settings import BaseSettings

CONFIG_PATH = Path("infra/config/newsdock.yaml")
SERVICES: dict[str, type[BaseSettings]] = {
    "ingester": IngesterSettings,
    "processor": ProcessorSettings,
    "sink": SinkSettings,
    "api": ApiSettings,
    "agent": AgentSettings,
}
# newsdock_db has no section of its own: its pool keys live under `common`.
COMMON_ONLY: list[type[BaseSettings]] = [DbSettings]
WEB_KEYS = {"api_base_url": None, "poll_ms": 60000, "page_size": None}

BANNED_STRINGS = {"gkg.raw", "gkg.clean", "gkg.dlq"}
BANNED_NAMES = {
    "MAX_ATTEMPTS",
    "RETENTION_DAYS",
    "FIRST_RUN_WINDOW",
    "MAX_PAYLOAD_BYTES",
    "DEFAULT_WINDOW",
    "RAW_TOPIC",
    "CLEAN_TOPIC",
    "DLQ_TOPIC",
}
WEB_BANNED = re.compile(r"\bPOLL_MS\b|NEXT_PUBLIC_API_BASE")


@dataclass(frozen=True)
class Violation:
    message: str
    path: str

    def __str__(self) -> str:
        return f"CFG {self.message}: {self.path}"


def _differs(key: str, value: Any, default: Any) -> str:
    return f"{key}={value!r} differs from the default {default!r}"


def _check_file(root: Path) -> list[Violation]:
    path = root / CONFIG_PATH
    where = str(CONFIG_PATH)
    if not path.is_file():
        return [Violation("config file missing", where)]
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        return [Violation(f"invalid YAML ({exc})", where)]
    found: list[Violation] = []
    known_anywhere: set[str] = set(WEB_KEYS)
    for cls in (*SERVICES.values(), *COMMON_ONLY):
        known_anywhere |= set(cls.model_fields)

    def walk_secrets(node: dict[str, Any], prefix: str) -> None:
        for key, value in node.items():
            if is_secret_name(str(key)):
                found.append(Violation(f"secret-looking key '{prefix}{key}'", where))
            if isinstance(value, dict):
                walk_secrets(value, f"{prefix}{key}.")

    walk_secrets(raw, "")

    for key, (value, dotted) in flatten(raw.get("common") or {}).items():
        if key not in known_anywhere:
            found.append(
                Violation(f"common.{dotted} is not a setting of any service", where)
            )
            continue
        for cls in (*SERVICES.values(), *COMMON_ONLY):
            info = cls.model_fields.get(key)
            if info is not None and info.default != value:
                found.append(
                    Violation(
                        _differs(f"common.{dotted}", value, info.default),
                        where,
                    )
                )
    for section, cls in SERVICES.items():
        for key, (value, dotted) in flatten(raw.get(section) or {}).items():
            info = cls.model_fields.get(key)
            if info is None:
                found.append(
                    Violation(
                        f"{section}.{dotted} is not a setting of {section}", where
                    )
                )
            elif info.default != value:
                found.append(
                    Violation(
                        _differs(f"{section}.{dotted}", value, info.default),
                        where,
                    )
                )
    for key, (value, dotted) in flatten(raw.get("web") or {}).items():
        if key not in WEB_KEYS:
            found.append(Violation(f"web.{dotted} is not a setting of web", where))
        elif WEB_KEYS[key] is not None and WEB_KEYS[key] != value:
            found.append(
                Violation(f"web.{dotted}={value!r} differs from the default", where)
            )
    unknown_sections = set(raw) - {"common", "web", *SERVICES}
    for section in sorted(unknown_sections):
        found.append(Violation(f"unknown section '{section}'", where))
    return found


def _python_sources(root: Path) -> Iterator[Path]:
    for base in (root / "apps", root / "packages"):
        if not base.is_dir():
            continue
        for path in base.glob("*/src/**/*.py"):
            rel = path.relative_to(root).as_posix()
            if path.name == "config.py" or "/newsdock_config/" in rel:
                continue
            yield path


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
            ):
                ids.add(id(body[0].value))
    return ids


def _check_python(root: Path) -> list[Violation]:
    found: list[Violation] = []
    for path in _python_sources(root):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text())
        docs = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docs
                and node.value in BANNED_STRINGS
            ):
                found.append(
                    Violation(
                        f"literal '{node.value}' (use settings)",
                        f"{rel}:{getattr(node, 'lineno', 0)}",
                    )
                )
            names: list[str] = []
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            for name in names:
                if name in BANNED_NAMES:
                    found.append(
                        Violation(
                            f"constant {name} (use settings)",
                            f"{rel}:{getattr(node, 'lineno', 0)}",
                        )
                    )
    return found


def _check_web(root: Path) -> list[Violation]:
    found: list[Violation] = []
    src = root / "apps" / "web" / "src"
    if not src.is_dir():
        return found
    for path in sorted([*src.rglob("*.ts"), *src.rglob("*.tsx")]):
        if ".test." in path.name:
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            match = WEB_BANNED.search(line)
            if match:
                rel = path.relative_to(root).as_posix()
                found.append(
                    Violation(
                        f"{match.group(0)} (use runtime config)", f"{rel}:{number}"
                    )
                )
    return found


def check(root: Path) -> list[Violation]:
    return [*_check_file(root), *_check_python(root), *_check_web(root)]


def main(root: Path | None = None) -> int:
    base = root if root is not None else Path(__file__).resolve().parents[2]
    violations = check(base)
    for violation in violations:
        print(violation)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
