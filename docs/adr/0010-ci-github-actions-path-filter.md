# ADR-0010: GitHub Actions with one workflow and path filtering

Status: **Accepted 2026-10-05** (user decision in `/spec-design foundation`)

## Context
AC-12 and AC-13: CI checks only what changed and builds only the changed image. `origin` is GitHub **[verified]**, so GitHub Actions **[assumption]**.

## Options
1. One `ci.yml`: a `changes` job using `dorny/paths-filter` v4.0.3 **[verified]**, conditional `check-python`, `check-web` and a matrix `build` per changed app, plus an aggregate `ci-ok` job.
2. Own script (`changed_apps.py`) computing the matrix from `git diff`; no third-party action, testable locally.
3. One workflow per app with `paths:` filters; required checks can stay pending when a workflow is skipped **[memory]**.

## Decision
Option 1. A change to `packages/core/**`, root `pyproject.toml` or `uv.lock` counts as a change to every Python app; `apps/web/**` only triggers web; a change to `Makefile` or the workflows (filter `tooling`) reruns both check jobs; a `docs` job always runs `make docs-check`. Implemented as designed in `.github/workflows/ci.yml` and covered by unit tests on the parsed filters; the workflow has not run on GitHub yet (see `verify.md`). `ci-ok` (`if: always()`, fails if any needed job failed) is the single required check. Actions pinned by major tag (`actions/checkout@v7`, `astral-sh/setup-uv@v10.2.0` (exact: the action publishes no floating major tag, found by the first CI run), `pnpm/action-setup@v6`, `docker/setup-buildx-action@v4`, `docker/build-push-action@v7` **[verified, latest releases]**); SHA pinning is backlog.

## Consequences
+ Little YAML, one required check, skipped jobs do not block merges. − One third-party action to trust; a CI-only path logic that is not testable locally (option 2 would be).
