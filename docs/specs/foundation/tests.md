# foundation — Tests

Derived from the Given/When/Then ACs in [spec.md](spec.md) §6 and the design in [design.md](design.md). Tasks that write each test: [plan.md](plan.md).

## 1. Test data and where it lives

M0 touches no GDELT data, so no real samples are needed (the real GKG sample stays in `docs/research.md` for M1).

| Kind | Where | Used by |
|---|---|---|
| Fake repo trees (valid and broken layouts) built in `tmp_path` | `infra/scripts/tests/` (builders in `conftest.py`) | TC-37…TC-41, TC-33…TC-35 |
| PATH stub directories with fake `docker`, `uv`, `pnpm`, `ollama` executables | `infra/scripts/tests/` (created in `tmp_path`) | TC-1…TC-3 |
| Deliberate violation files (unique temp names, removed in `finally`) written into the real tree | `infra/scripts/tests/rules/` | TC-10, TC-14, TC-15, TC-42…TC-44 |
| Real tools and containers (uv, pnpm, Docker Desktop, Kafka, Postgres) | no fakes; marker `docker` for Docker tests | TC-5…TC-9, TC-16…TC-28 |
| Parsed `ci.yml` | `infra/scripts/tests/test_ci_workflow.py` | TC-29, TC-30 |

**Markers** (registered in the root `pyproject.toml`): `rules` (mutation tests, `make test-rules`), `docker` (need Docker, `make test-infra`). `make check` runs everything else. Python app smoke tests live in each app's `tests/unit/` (DR-10).

## 2. Test cases

Levels: unit / integration / manual. Written test-first in the task named in the last column.

| TC | AC | Level | Case | Task |
|---|---|---|---|---|
| TC-1 | AC-1 | unit | Given a PATH without `pnpm`, When `doctor.sh` runs, Then exit 1 and the output names `pnpm` with an install hint | T-06 |
| TC-2 | AC-1 | unit | Given a PATH missing `docker` and `uv`, When doctor runs, Then both are listed in one run (not just the first) | T-06 |
| TC-3 | AC-1 | unit | Given `docker` on PATH but `docker info` failing, When doctor runs, Then exit 1 and the output says the daemon is unreachable | T-06 |
| TC-4 | AC-2 | manual | Given the owner's machine as the README says, When `make doctor` runs, Then exit 0, versions of Docker, Compose, uv, pnpm, resolved Python 3.12+ and Node 24, and Ollama model names are printed | T-14 (dry run), verified in `/spec-verify` |
| TC-5 | AC-3 | integration | Given a fresh checkout, When `make setup-python` runs, Then one environment can import `newsdock_core`, `newsdock_db` and all five `newsdock_<app>` packages | T-03 |
| TC-6 | AC-3 | integration | Given `apps/web` with its lockfile, When `make setup-web` runs, Then dependencies install with `--frozen-lockfile`; with a deliberately stale lockfile it exits non-zero | T-07 |
| TC-7 | AC-4 | integration | Given the Python skeletons, When `make check-python` runs, Then ruff lint, ruff format check, mypy, import-linter, layout check and pytest all run and the exit code is 0 | T-04 |
| TC-8 | AC-4 | integration | Given the web skeleton, When `make check-web` runs, Then lint, format check, typecheck and test run and exit 0 | T-07 |
| TC-9 | AC-4 | integration | Given all skeletons, When `make check` runs, Then `check-python`, `check-web` and `docs-check` all ran and the exit code is 0; `make -n check` lists every sub-check | T-12 |
| TC-10 | AC-5 | integration (`rules`) | Given a type error in a temp file inside `apps/sink`, When `make check-python` runs, Then exit non-zero and the output names that file and `newsdock_sink` | T-04 |
| TC-11 | AC-6 | integration | Given each of the five Python apps, When `make test APP=<name>` runs, Then ≥ 1 test runs and passes (parametrized) | T-03 |
| TC-12 | AC-6 | integration | Given `apps/web`, When `make test APP=web` runs, Then ≥ 1 test passes | T-07 |
| TC-13 | AC-6 | unit | Given `APP=nosuchapp`, or an app with no collected tests, When `make test` runs, Then exit non-zero with a clear message | T-03 |
| TC-14 | AC-7 | integration (`rules`) | Given a temp module in `newsdock_api.adapters` importing `newsdock_sink`, When import-linter runs, Then exit non-zero naming both apps and DR-7 | T-04 |
| TC-15 | AC-7 | integration (`rules`) | Given the same module importing `newsdock_core` instead, When import-linter runs, Then it passes (negative control) | T-04 |
| TC-16 | AC-8 | integration (`docker`) | Given Docker running and no `.env`, When `make build` runs, Then six images `newsdock-<app>:dev` exist and exit 0 | T-08 |
| TC-17 | AC-8 | integration (`docker`) | Given `make build APP=api`, Then only the `api` image is built | T-08 |
| TC-18 | AC-8 | integration (`docker`) | Given a built image, Then it runs as a non-root user, contains no `.env`, and `docker run` of the default command exits 0 (security) | T-08 |
| TC-19 | AC-9 | integration (`docker`) | Given `.env` from `.env.example`, When `make up` completes, Then `kafka` and `postgres` are healthy and `pg_available_extensions` lists `vector` | T-09 |
| TC-20 | AC-9 | integration | Given no `.env`, When `make up` runs, Then exit non-zero and the message says to copy `.env.example` | T-09 |
| TC-21 | AC-9 | integration (`docker`) | Given the stack is up, Then every published port is bound to `127.0.0.1` (security) | T-09 |
| TC-22 | AC-9 | integration (`docker`) | Given `make down` then `make up`, Then the stack is healthy again and Postgres data created before survives (recovery) | T-09 |
| TC-23 | AC-10 | integration (`docker`) | Given Kafka healthy, When topic setup runs, Then `gkg.raw`, `gkg.clean`, `gkg.dlq` exist with 1 partition and replication 1 | T-10 |
| TC-24 | AC-10 | integration (`docker`) | Given the topics exist, When topic setup runs a second time, Then exit 0 and the topic descriptions are unchanged | T-10 |
| TC-25 | AC-10 | integration (`docker`) | Given Kafka just started, When the `topics` job starts immediately, Then it waits for health and still succeeds (edge) | T-10 |
| TC-26 | AC-11 | integration (`docker`) | Given Postgres healthy, When `make migrate` runs twice, Then `alembic_version` holds exactly `0001`, extension `vector` exists, and both runs exit 0 | T-11 |
| TC-27 | AC-11 | integration (`docker`) | Given Postgres stopped, When `make migrate` runs, Then exit non-zero (failure) | T-11 |
| TC-28 | AC-11 | unit | Given `DATABASE_URL` in the environment, When `newsdock_db.config` loads, Then the URL is exposed; `infra/migrations/env.py` reads it only through that module (DR-9) | T-11 |
| TC-29 | AC-12 | unit | Given the parsed `ci.yml` filters, When only `apps/web/**` files change, Then `web` is true and `python` and every app flag are false | T-13 |
| TC-30 | AC-13 | unit | Given the filters, When only `apps/api/**` changes Then the build matrix is `[api]`; When `packages/core/**`, root `pyproject.toml` or `uv.lock` change, Then all five Python apps are in the matrix | T-13 |
| TC-31 | AC-12 | manual | Given a real pull request that changes only `apps/web`, When CI runs on GitHub, Then web check runs and Python checks are skipped, `ci-ok` passes | `/spec-verify` |
| TC-32 | AC-13 | manual | Given a real pull request that changes only `apps/api`, When CI runs, Then only the `api` image builds, `ci-ok` passes | `/spec-verify` |
| TC-33 | AC-14 | unit | Given the real repo, When `make docs-check` runs, Then exit 0 | T-12 |
| TC-34 | AC-14 | unit | Given a fake tree whose app README lacks `Entrypoint`, When docs-check runs, Then exit non-zero naming file and section | T-12 |
| TC-35 | AC-14 | unit | Given a fake tree with a broken relative link in a README, When docs-check runs, Then exit non-zero naming file and link | T-12 |
| TC-36 | AC-15 | manual | Given a clean clone and only `README.md`, When a person follows its steps, Then `make check` is green and `make up` is healthy | T-14 (dry run), verified in `/spec-verify` |
| TC-37 | AC-16 | unit | Given a fake tree with a Python file outside `src/newsdock_<app>/` or `tests/` in an app, When `check_layout.py` runs, Then exit non-zero naming DR-4 and the path | T-05 |
| TC-38 | AC-16 | unit | Given an app missing `README.md` (and another missing `tests/`), Then DR-3 and the path are reported | T-05 |
| TC-39 | AC-16 | unit | Given an unlisted top-level folder or file, Then DR-1 is reported | T-05 |
| TC-40 | AC-16 | unit | Given `apps/extra`, Then DR-2 is reported; Given an app absent from the import-linter contracts, Then the check fails naming the app | T-05 |
| TC-41 | AC-16 | unit | Given Python files in `infra/scripts/` and `infra/migrations/`, and tools' cache dirs (`.venv`, `.mypy_cache`, `node_modules`), Then no violation is reported (edge, negative control) | T-05 |
| TC-42 | AC-17 | integration (`rules`) | Given `domain/` importing `httpx` or `sqlalchemy`, or its own `adapters`, or `newsdock_db`, When import-linter runs, Then exit non-zero naming DR-6 and the file | T-04 |
| TC-43 | AC-17 | integration (`rules`) | Given `newsdock_core` importing an app, `newsdock_db`, or `sqlalchemy`, Then exit non-zero naming DR-7 and the file | T-04 |
| TC-44 | AC-17 | integration (`rules`) | Given `os.environ` or `os.getenv` outside `config.py`, When ruff runs, Then it fails naming DR-9; the same lines inside `config.py` pass (negative control) | T-04 |

**Coverage:** every AC-1…AC-17 has ≥ 1 test and every TC names an AC (checked in plan.md "Plan validation"). Positive controls (TC-15, TC-41, TC-44 config case) guard against rules that fail everything.

## 3. Manual checklists (`Verify: manual`)

**AC-2 / TC-4**
- [ ] Docker Desktop running; `make doctor` prints Docker, Compose, uv, pnpm versions and exits 0
- [ ] Output shows Python 3.12.x (from uv) and Node 24.x (from pnpm), not the system Node 26
- [ ] Ollama listed with at least one model; evidence: terminal output saved in `verify.md`

**AC-12 / TC-31 and AC-13 / TC-32** (needs the repo pushed to GitHub)
- [ ] PR touching only `apps/web`: `check-web` runs, `check-python` and `build` are skipped, `ci-ok` is green
- [ ] PR touching only `apps/api`: `check-python` runs, `build` matrix has only `api`, `ci-ok` is green
- [ ] PR touching `packages/core`: all five Python images in the matrix
- [ ] Evidence: links to the three workflow runs in `verify.md`

**AC-15 / TC-36** (fresh clone in an empty directory, README only)
- [ ] Prerequisite section lists every manual install (Docker Desktop, Ollama, uv, pnpm)
- [ ] `make doctor`, `make setup`, `make check`, `make build`, `cp .env.example .env`, `make up` succeed in that order with no other document opened
- [ ] `make down` stops everything; a second `make up` works
- [ ] Time to green and any stumbling points noted in `verify.md`

## 4. Measurements (provisional targets: measure, not pass/fail)

| Target | What | How | Where recorded |
|---|---|---|---|
| M-1 | `make check` duration on the skeletons | run 3×, record median, cold and warm caches | `verify.md` |
| M-2 | `make build` duration, cold and warm; image size per app | `time make build`, `docker image ls newsdock-*` | `verify.md` |
| M-3 | `make up` time to healthy | `time make up` from `down` | `verify.md` |
| M-4 | CI wall time: one-app change vs full run | GitHub Actions run durations for the TC-31/TC-32 PRs and a core change | `verify.md` |
