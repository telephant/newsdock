# foundation — Design (Milestone 0)

Status: **approved** · 2026-10-05 · Spec: [spec.md](spec.md) · Detail (not required reading): [design-detail.md](design-detail.md)

**Reading order:** this file → `diagrams/index.html` (open in a browser; each diagram has a "Check" box) → ADRs 0005–0010 in `../../adr/` → answer the checklist at the bottom.

## 1. Components

M0 has no runtime services of its own; its components are the tools and files that make the repo buildable. Ids `C-n` are used in all foundation docs.

| Id | Component | Job | Notes |
|---|---|---|---|
| C-1 | Command runner (`Makefile`) | One entry point: `doctor setup check test build up down topics migrate docs-check` | GNU Make 3.81 compatible; `check` = `check-python` + `check-web` + `docs-check` |
| C-2 | Doctor (`infra/scripts/doctor.sh`) | Verify Docker, Compose, uv, pnpm, Ollama; print resolved Python and Node | Python 3.12 and Node are provisioned by uv and pnpm, not required on PATH |
| C-3 | Python workspace (root `pyproject.toml` + `uv.lock`) | One environment for 5 apps + `newsdock_core` + `newsdock_db` | `exclude = ["apps/web"]`; `uv sync --all-packages` (ADR-0007) |
| C-4 | Python quality gate | ruff (lint, format, `TID251`), mypy strict, pytest, import-linter, `infra/scripts/check_layout.py` | Enforces DR-1…DR-9 (ADR-0006/0007) |
| C-5 | Web app + gate (`apps/web`) | Next.js scaffold; ESLint, Prettier, `tsc`, Vitest | Node pinned by pnpm `devEngines.runtime` (ADR-0009) |
| C-6 | App images (6 Dockerfiles, `.dockerignore`) | `make build` builds every app image | Context = repo root; compose profile `apps` |
| C-7 | Compose infra (`infra/compose.yaml`) | `kafka` (KRaft), `postgres` (pgvector), one-shot jobs `topics`, `migrate` | Ports bound to 127.0.0.1; apps defined but not started |
| C-8 | Migrations (`infra/migrations/`, Alembic) + `packages/db` | Revision `0001` creates the `vector` extension; `newsdock_db` holds config, engine factory, empty `MetaData` | ADR-0008 |
| C-9 | CI (`.github/workflows/ci.yml`) | Path-filtered check and image build, one `ci-ok` gate | ADR-0010 |
| C-10 | Docs | `README.md`, six app READMEs, `docs/README.md` index, `infra/scripts/check_docs.py` (`make docs-check`) | DR-13 |

## 2. Key flows

- **F-1 First-time setup:** `make doctor` → `make setup` → `make check`. (Diagrams 1, 2)
- **F-2 Daily loop:** edit → `make check` (or `make test APP=<name>`). (Diagram 3 shows the import rules it enforces)
- **F-3 Infra loop:** `make build` → `make up` (infra, then `topics`, then `migrate`) → `make down`. (Diagrams 2, 5, 6)
- **F-4 Pull request:** `changes` job → conditional checks and image builds → `ci-ok`. (Diagram 4)

## 3. Contracts

**Make targets** (names fixed by the spec)

| Target | Does | Exit non-zero when |
|---|---|---|
| `doctor` | tool and version report | a tool is missing (names it and the install hint) |
| `setup` (= `setup-python` + `setup-web`) | `uv sync --all-packages --locked`; `pnpm install --frozen-lockfile` in `apps/web` | lockfile out of date |
| `check` / `check-python` / `check-web` | lint, format check, types, tests, import rules, layout | any check fails (output names app and rule) |
| `test APP=<name>` | that app's tests only | a test fails or none ran |
| `build [APP=<name>]` | `docker compose --profile apps build` | an image fails to build |
| `up` / `down` | start / stop infra; `up` runs `topics` and `migrate` | `.env` missing, a service not healthy |
| `topics`, `migrate` | one-shot jobs via `docker compose run --rm` (`migrate` = `alembic upgrade head` in its own small image) | job fails |
| `docs-check` | README sections and relative links | missing section or broken link |
| `test-rules` | mutation tests that prove each enforced rule fails (marker `rules`) | a rule does not fail when violated |
| `test-infra` | Docker-based tests (marker `docker`) | a stack or image test fails |

**Infra contract:** topics `gkg.raw`, `gkg.clean`, `gkg.dlq`, 1 partition, replication 1. Migrations `infra/migrations/versions/NNNN_<name>.py` (revision ids `0001`…); current revision in `alembic_version`. Env keys in `.env.example`: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` (default 5433), `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS` (placeholders only).

**Rule → enforcer map** (rules are in spec §6): DR-1…DR-4 `check_layout.py`; DR-6, DR-7 import-linter contracts; DR-9 ruff `TID251`; DR-13 `check_docs.py`; DR-5, DR-8, DR-10…DR-12 review.

## 4. Tricky parts (all found by prototype, ADR-0007 **[verified]**)

- **uv workspace:** glob `apps/*` fails on `apps/web` without `pyproject.toml` → `exclude`. Without `--all-packages` the apps are not installed and import-linter finds nothing.
- **Test names:** equal file names in two apps collide → pytest `--import-mode=importlib`.
- **External-library rules:** import-linter must set `include_external_packages = true` or `domain/` could import `httpx` unnoticed.
- **Images in a workspace:** build context is the repo root; the Dockerfile copies only the root `pyproject.toml`, `uv.lock` and the manifests of the app and its workspace dependencies (explicit `COPY` lines), syncs dependencies with `--no-install-workspace`, then copies sources and syncs again with `--no-editable --package newsdock-<app>` **[verified, T-01]**.
- **One-shot jobs:** `topics` and `migrate` run through `docker compose run --rm`, not `up --wait`, so a job that exits 0 is not mistaken for an unhealthy service **[verified, T-01: jobs ran with `docker compose run --rm`; `up --wait` is used only for `kafka postgres`]**.
- **Node:** pnpm downloads Node 24 (LTS) from `devEngines.runtime`; the machine's Node 26 is ignored.

## 5. Top failure modes

| Failure | Effect | Handling |
|---|---|---|
| Docker not running | `build`, `up` fail | `doctor` reports daemon unreachable |
| `.env` missing | `up` fails | clear message: copy `.env.example` |
| Kafka slow to start | topic job races | `topics` waits for `kafka` healthy |
| Lockfile stale | `setup` fails | `--locked` / `--frozen-lockfile` print the fix |
| Rule violated | `check` fails | message names rule id and file (AC-16, AC-17) |
| CI path filter misses a dependency | wrong job skipped | core, root `pyproject.toml`, `uv.lock` map to all Python apps |

## 6. Technology

uv 0.12.23, ruff 0.16.10, mypy 2.4.0, pytest 9.1.1, import-linter 2.15 **[verified, PyPI]**; pnpm 12.9.1, Next.js 16.3.8, TypeScript ^5 (5.9.3) and ESLint ^9 (9.39.5; 10.x and TypeScript 7 break the lint setup, ADR-0009), Prettier 3.9.9, Vitest 5.0.3, Node 24.21.0 via pnpm **[verified, T-02]**; Docker Desktop 4.93 **[verified cask; macOS compatibility assumption]**; `apache/kafka` 4.2.2, `pgvector/pgvector` 0.8.7-pg16-trixie, SQLAlchemy 2.1.3, Alembic 1.20.0, psycopg 3.3.6 **[verified, PyPI]**; `python:3.12-slim`, `node:24-slim` **[verified tags]**; GitHub Actions per ADR-0010 **[verified releases]**; GNU Make 3.81 **[verified]**. Not chosen: `just`, dbmate, psycopg-only access, Biome, pyright, Flink.

## 7. AC coverage

| AC | Covered by | Where |
|---|---|---|
| AC-1 | C-2 | doctor |
| AC-2 | C-2 | doctor |
| AC-3 | C-3, C-5, C-1 | `make setup` |
| AC-4 | C-4, C-5, C-1 | `make check` |
| AC-5 | C-4 | mypy |
| AC-6 | C-4, C-5 | `make test APP=` |
| AC-7 | C-4 | import-linter independence contract |
| AC-8 | C-6 | `make build` |
| AC-9 | C-7 | `make up` |
| AC-10 | C-7 | `topics` job |
| AC-11 | C-8, C-7 | `migrate` job |
| AC-12 | C-9 | `changes` job |
| AC-13 | C-9 | build matrix |
| AC-14 | C-10 | `docs-check` |
| AC-15 | C-1…C-10 | README flow |
| AC-16 | C-4 | `check_layout.py` |
| AC-17 | C-4 | import-linter + ruff `TID251` |

## 8. Questions to answer before approving this design

- [x] ADR-0007: ruff + mypy strict + pytest + import-linter for Python?
- [x] ADR-0008: SQLAlchemy 2 + Alembic (user decision 2026-10-05, replaces the dbmate proposal)?
- [x] Accept the new shared package `packages/db` (`newsdock_db`) and a migration image `infra/migrations/Dockerfile` (not one of the six apps)?
- [x] ADR-0009: ESLint + Prettier + Vitest, Node 24 pinned by pnpm?
- [x] ADR-0010: one workflow with `dorny/paths-filter` and an aggregate `ci-ok` check?
- [x] Python 3.12 and Node provisioned by uv and pnpm instead of required on PATH (AC-1, AC-2 wording and D-5 note updated)?
- [x] `infra/scripts/` (doctor, layout and docs checks) and the changed root-file lists in DR-1 and DR-11 (applied to the spec)?
- [x] App services defined now under compose profile `apps` (build only), started in M1?
- [x] No pnpm workspace: `apps/web` is a standalone pnpm project with its own lockfile?
