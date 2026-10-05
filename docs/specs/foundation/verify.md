# foundation — Verification

Verified 2026-10-05 on commit `5fcbe7a` (branch `docs/foundation-plan`, not pushed) plus uncommitted doc-drift fixes. Machine: macOS 26.5.1 arm64, Docker Desktop 4.93.0 (engine 29.8.1).

## Verdict: **pending, 2 ACs need GitHub** (AC-12, AC-13)

15 of 17 ACs are verified. AC-12 and AC-13 can only be proven by real pull requests; the owner chose to pause, push and open them, then re-run `/spec-verify foundation`. Nothing found so far is a defect: the unit proxies for AC-12/13 pass, and the workflow just has not run on GitHub yet. If the first CI run is clean the verdict becomes **pass**.

## Runs in this session

| Command | Result |
|---|---|
| `make check` | exit 0: ruff, mypy strict (64 files), import-linter (3 contracts kept, 0 broken), layout check, 86 Python tests, web lint + format + typecheck + Vitest (1 test), docs-check |
| `make test-rules` | 20 passed (about 11 s); no leftover violation files |
| `make test-infra` | 22 passed (2 min 46 s); no containers or volumes left behind |
| README-only run in a real `git clone` of the committed branch (no `.venv`, no `node_modules`) | `make doctor`, `make setup`, `make check`, `make build`, `cp .env.example .env`, `make up` (Kafka and Postgres healthy, revision `0001`), `make down`, `make up` again: all exit 0, 64 s total with warm tool caches |

## Results

| AC | TC | Result | Evidence |
|---|---|---|---|
| AC-1 | TC-1, TC-2, TC-3 | **passing** | `test_doctor.py` (stubbed PATH: missing pnpm, missing docker + uv listed together, daemon unreachable) in `make check` |
| AC-2 | TC-4 | **manual-ok** | `make doctor` exit 0: Docker 29.8.1, Compose v5.5.1, uv 0.12.23, pnpm 12.9.1, Python 3.12.14 (resolved by uv), Node 24.x (pinned by pnpm), `ollama: models: llama3.2:1b`. System `node -v` is v26.9.0 while `pnpm --dir apps/web exec node -v` is v24.21.0 |
| AC-3 | TC-5, TC-6 | **passing** | `test_workspace_imports.py`; `test_web.py::setup` (frozen lockfile, stale lockfile fails) |
| AC-4 | TC-7, TC-8, TC-9 | **passing** | `make check` exit 0; `test_check_green.py`; `test_check_docs.py::test_make_check_runs_docs_check` |
| AC-5 | TC-10 | **passing** | `test_rules.py::test_type_error_fails_and_names_the_app` |
| AC-6 | TC-11, TC-12, TC-13 | **passing** | `test_make_test.py` (5 apps, unknown app, missing APP, no tests ran); `test_web.py::make test APP=web` |
| AC-7 | TC-14, TC-15 | **passing** | import-linter contract "DR-7 apps are independent" broken by a temp import, kept by the core import |
| AC-8 | TC-16, TC-17, TC-18 | **passing** | `test_images.py` (13 tests: all images built with no `.env`, `APP=api` builds only api, non-root, no `.env`, default command exits 0); web image also served HTTP 200 |
| AC-9 | TC-19…TC-22 | **passing** | `test_stack.py` (healthy, `vector` available, no `.env` message, ports on 127.0.0.1, down then up keeps data) |
| AC-10 | TC-23, TC-24, TC-25 | **passing** | `test_stack.py` (3 topics with 1 partition, second run unchanged, job after Kafka restart) |
| AC-11 | TC-26, TC-27, TC-28 | **passing** | `test_stack.py` (revision `0001` once, `vector`, fails with Postgres stopped); `packages/db` unit tests; `test_migration_files.py` |
| AC-12 | TC-29 / TC-31 | **in-progress** | TC-29 (unit proxy on the parsed path filters) passes. TC-31 (real PR changing only `apps/web`) not run: branch is not on GitHub |
| AC-13 | TC-30 / TC-32 | **in-progress** | TC-30 passes (api-only gives matrix `[api]`; core, `pyproject.toml`, `uv.lock` give all five Python apps). TC-32 not run |
| AC-14 | TC-33, TC-34, TC-35 | **passing** | `test_check_docs.py` (real repo, missing section, broken link); `make docs-check` exit 0 |
| AC-15 | TC-36 | **manual-ok** | README-only run in a real `git clone` of the committed branch, see "Runs"; caveat: the clone is of a local commit, not of a pushed one |
| AC-16 | TC-37…TC-41 | **passing** | `test_check_layout.py` (12 tests incl. the real repo) |
| AC-17 | TC-42, TC-43, TC-44 | **passing** | `test_rules.py` (domain purity, core cleanliness, `os.environ`/`os.getenv` outside `config.py`, with negative controls) |

Notes: import-linter reports the violating module name, not a file path (equivalent for AC-17). A multi-part AC counts as passing only because every part's test ran in this session.

## Measurements (provisional targets: for information, not pass/fail)

| ID | What | Result |
|---|---|---|
| M-1 | `make check` duration | warm: 10 s, 8 s, 8 s (median 8 s). Fresh clone after `make setup`: 24 s (uv and pnpm download caches were warm) |
| M-2 | `make build` | no-cache build of all 7 images: 29 s; warm layer cache: 10 s. Sizes: five Python apps 229 MB each, `migrate` 311 MB, `web` 402 MB |
| M-3 | `make up` to healthy | 12 s and 13 s from `down` (includes topics and migrate; images already present). First pull of the Kafka and Postgres images took about 33 s in the T-01 spike |
| M-4 | CI wall time | **not measured**: no GitHub run yet |

## Doc drift

| # | Finding | Status |
|---|---|---|
| D-1 | `design.md` make-target table lacked `lint-python`, `types-python`, `imports-python`, `layout-python`, `help` | fixed |
| D-2 | `design-detail.md` §6 described an inline topic loop; the code uses the mounted script `infra/kafka/create-topics.sh` | fixed |
| D-3 | CI: the `tooling` filter and the `docs` job were missing from `design-detail.md` §7 and ADR-0010 | fixed |
| D-4 | ADR-0007 and design-detail §2/§3 lacked the pydantic mypy plugin, `pythonpath`, empty `PENDING_UNTIL`, ignored caches; `os.getenv` ban was still tagged assumption | fixed |
| D-5 | Versions in README match `uv.lock` and the images (SQLAlchemy 2.1.3, Alembic 1.20.0, psycopg 3.3.6, Next 16.3.8, Node 24.21.0) | no drift |
| D-6 | M1 docs are stale for M0 decisions (`mvp/design-detail.md` §8 tooling, `packages/db`, SQLAlchemy Core versus ORM, two Design TODOs) | **open**, belongs to `/spec-design mvp` |

Scope: nothing outside the spec was implemented (extras are `make help` and the granular `*-python` targets already in the design); no backlog item leaked into code (grep for OpenAPI, heartbeat, pre-commit, Dependabot, gitleaks, trivy in code: none).

## To finish verification (owner)

1. Put the work on GitHub and let the first run validate the workflow: `git switch main && git merge --ff-only docs/foundation-plan && git push origin main` (a push to `main` runs the full workflow).
2. Open three small pull requests against `main` that each change one file: `apps/web/README.md` only (expect `check-web` and the web build only), `apps/api/README.md` only (expect `check-python` and the api build only), `packages/core/README.md` only (expect all five Python builds, no web build). Each must end with `ci-ok` green.
3. Re-run `/spec-verify foundation`: it will read the runs, fill M-4 and settle AC-12 and AC-13.
