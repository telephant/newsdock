# ADR-0007: Python toolchain: uv, ruff, mypy, pytest, import-linter

Status: **Accepted 2026-10-05** (user decision in `/spec-design foundation`)

## Context
`make check` must lint, format, type check, test and enforce AC-7, AC-16, AC-17 across five apps and `newsdock_core`. Prototyped in a scratch uv workspace on 2026-10-05: all rule violations below were caught **[verified]**.

## Options
1. ruff (lint + format + `TID251` banned-api) + mypy strict + pytest + import-linter. Versions: ruff 0.16.10, mypy 2.4.0, pytest 9.1.1, import-linter 2.15 **[verified, PyPI]**.
2. As 1 but pyright 1.1.414 for types.
3. As 1 but `ty` 0.0.84 or `pyrefly` 1.3.2 for types (both pre-1.0 numbering **[verified version numbers]**).

## Decision
Option 1. Findings from the prototype: `members = ["apps/*", "packages/*"]` needs `exclude = ["apps/web"]` (uv errors on a member without `pyproject.toml`); `uv sync --all-packages` is required or import-linter cannot find the apps; pytest needs `--import-mode=importlib` for equal test file names in different apps; mypy needs `explicit_package_bases` + `mypy_path`; import-linter needs `include_external_packages = true` to forbid I/O libraries; `os.environ` is banned by `TID251` with a per-file ignore for `config.py`.

## Consequences
+ Mature, fast tools; one `pyproject.toml` at the root; each rule maps to one contract. − Two config styles (ruff rules and import-linter contracts); layout rules (DR-1…DR-4) need a ~60-line stdlib script `infra/scripts/check_layout.py` because no tool covers them. Switching the type checker later is cheap.
