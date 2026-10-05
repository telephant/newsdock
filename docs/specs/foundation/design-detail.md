# foundation — Design detail

**Reference only. Not required reading for design approval.** Overview: [design.md](design.md).

## 1. Final repository tree (after M0)

```
newsdock/
  Makefile  pyproject.toml  uv.lock  .python-version  .env.example  .gitignore  .dockerignore  README.md  CLAUDE.md
  .github/workflows/ci.yml
  apps/{ingester,processor,sink,api,agent}/   pyproject.toml  Dockerfile  README.md  src/newsdock_<app>/{__init__,__main__,config}.py, domain/, adapters/   tests/{unit,integration}/
  apps/web/            package.json  pnpm-lock.yaml  Dockerfile  README.md  src/{app,features,components,lib/api}
  packages/core/       pyproject.toml  src/newsdock_core/{gkg,urls,models,contracts}/  tests/fixtures/
  packages/db/         pyproject.toml  src/newsdock_db/{config.py,engine.py,metadata.py}  tests/
  infra/               compose.yaml  kafka/  scripts/{doctor.sh,check_layout.py,check_docs.py}
  infra/migrations/    alembic.ini  env.py  script.py.mako  Dockerfile  versions/0001_baseline.py
  docs/                README.md  roadmap.md  research.md  specs/  adr/
```

Spec adjustments made 2026-10-05 (approved): DR-1 root files = `Makefile`, `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `.gitignore`, `.dockerignore`, `README.md`, `CLAUDE.md` (no `pnpm-workspace.yaml`: `apps/web` is a standalone pnpm project with its own lockfile); DR-11 adds `scripts/` and an Alembic `migrations/` project (ADR-0008).

## 2. Root `pyproject.toml` (prototyped, all checks ran **[verified]**)

```toml
[tool.uv]
package = false
[tool.uv.workspace]
members = ["apps/*", "packages/*"]
exclude = ["apps/web"]
[dependency-groups]
dev = ["ruff", "mypy", "pytest", "import-linter"]
[tool.ruff.lint]
select = ["E", "F", "I", "TID"]
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"os.environ".msg = "DR-9: read env only in config.py"
"os.getenv".msg = "DR-9: read env only in config.py"      # [verified in T-04]
[tool.ruff.lint.per-file-ignores]
"**/config.py" = ["TID251"]
[tool.mypy]
strict = true
plugins = ["pydantic.mypy"]   # needed for pydantic-settings classes (T-11)
explicit_package_bases = true
mypy_path = ["apps/ingester/src", "...", "packages/core/src"]
[tool.pytest.ini_options]
addopts = "--import-mode=importlib"
testpaths = ["apps", "packages", "infra/scripts"]
pythonpath = ["infra/scripts"]   # lets tests import check_layout and check_docs
```

**import-linter** (`include_external_packages = true`, `root_packages` = every `newsdock_*`):

| Contract | Type | Rule | Violation caught in prototype |
|---|---|---|---|
| apps independent | independence | `newsdock_{ingester,processor,sink,api,agent}` | `newsdock_api.adapters.bad -> newsdock_sink` |
| core is clean | forbidden | source `newsdock_core`; forbidden: every app, `newsdock_db`, `confluent_kafka`, `psycopg`, `sqlalchemy`, `alembic`, `httpx`, `fastapi` | `newsdock_core.bad -> newsdock_api` |
| domain is pure | forbidden | source `newsdock_<app>.domain`; forbidden: its `adapters`, `newsdock_db`, same I/O libraries | `newsdock_sink.domain.bad -> httpx` |

Wildcards in contracts (`newsdock_*.domain`) are not needed: list modules explicitly and let `check_layout.py` fail when a new app is not listed **[assumption]**. Other violations seen: `os.environ` outside `config.py` → ruff `TID251`; type error → mypy `return-value`.

## 3. `check_layout.py` (stdlib only, ~60 lines)

| Rule | Check | Message |
|---|---|---|
| DR-1 | top-level entries ⊆ allowed folders + allowed root files | `DR-1 unexpected top-level entry: <name>` |
| DR-2 | `apps/*` names ⊆ the six fixed names | `DR-2 unknown app: <name>` |
| DR-3 | required skeleton files exist per app type | `DR-3 apps/<app> missing <path>` |
| DR-4 | every `*.py` under an app is below `src/newsdock_<app>/` or `tests/`; Python apps contain `domain/` and `adapters/` | `DR-4 <path> outside src/ or tests/` |

Also fails if an app is missing from the import-linter contracts (keeps AC-7 honest). `PENDING_UNTIL` (required items later tasks create) is empty after T-08. Tool caches (`.import_linter_cache`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.next`) are ignored. mypy also covers `infra/migrations`. Own unit tests live in `infra/scripts/tests/`.

## 4. Makefile and doctor

- Targets as in design.md §3; `.PHONY`; plain recipes (no `.ONESHELL`, no `$(file ...)`) for Make 3.81 **[verified: 3.81]**. `make help` lists targets from `##` comments.
- `check-python`: `uv run ruff check .` · `ruff format --check .` · `mypy` · `lint-imports` · `pytest` · `python infra/scripts/check_layout.py`. `check-web`: `pnpm --dir apps/web run lint | format:check | typecheck | test`. `check`: both plus `docs-check`.
- `test APP=x`: `uv run pytest apps/x` (or `pnpm --dir apps/web test` for `web`); fails when zero tests ran.
- `doctor.sh`: for each of `docker` (+ `docker compose version`, `docker info` reachable), `uv`, `pnpm`, `ollama` run `command -v`; on miss print `MISSING <tool>: <install hint>` (brew cask/formula names verified 2026-10-05) and exit 1 after listing all. Then print versions, `uv python find ">=3.12"`, Node from `apps/web/package.json` `devEngines`, and Ollama models via `ollama list` (AC-2).

## 5. Images

- **Python apps:** `python:3.12-slim` (build and runtime stages); uv copied from `ghcr.io/astral-sh/uv:0.12.23` (multi-arch amd64 + arm64 **[verified, T-01]**). Layer 1 copies only the root `pyproject.toml`, `uv.lock`, and the `pyproject.toml` of the app and of each workspace package it depends on, one explicit `COPY` per file (a wildcard such as `COPY apps/*/pyproject.toml` flattens the paths), then `uv sync --frozen --no-dev --no-install-workspace --package newsdock-<app>`. Layer 2 copies `packages/*/src` (those needed) and `apps/<app>/src`, then `uv sync --frozen --no-dev --no-editable --package newsdock-<app>`. Final stage copies `/app/.venv`, runs as a non-root user (uid 1000), `CMD ["python", "-m", "newsdock_<app>"]`. **[verified, T-01]**: a build with only the api and core manifests present (sink and web manifests absent) succeeds, installs exactly `newsdock-api` and `newsdock-core`, and the image runs as uid 1000 and contains no `.env`.
- **Web:** `node:24-slim`; pnpm install with frozen lockfile; `next build` with `output: "standalone"` **[memory]**; runs as non-root.
- `.dockerignore`: `.git`, `.venv`, `node_modules`, `.env*` (keeps secrets out of images).
- `infra/migrations/Dockerfile`: the migration image (not an app); built by `make build` and in CI when `infra/migrations/**` or `packages/db/**` changes.
- Compose profile `apps` defines `build` + `image: newsdock-<app>:dev` for all six; M1 adds runtime config.

## 6. `infra/compose.yaml`

| Service | Image | Notes |
|---|---|---|
| `kafka` | `apache/kafka:4.2.2` | KRaft single node **[verified, T-01]** with: `KAFKA_NODE_ID=1`, `KAFKA_PROCESS_ROLES=broker,controller`, `KAFKA_LISTENERS=INTERNAL://:9092,CONTROLLER://:9093,EXTERNAL://:29092`, `KAFKA_ADVERTISED_LISTENERS=INTERNAL://kafka:9092,EXTERNAL://127.0.0.1:29092`, `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT`, `KAFKA_INTER_BROKER_LISTENER_NAME=INTERNAL`, `KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER`, `KAFKA_CONTROLLER_QUORUM_VOTERS=1@kafka:9093`, the three replication/ISR settings = 1, `KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0`. Containers use `kafka:9092`; host tools use `127.0.0.1:29092` (published only on 127.0.0.1); both worked, the host side with `confluent-kafka` 2.15.1 on Python 3.12 arm64. Healthcheck **[verified]**: `/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092` (interval 5 s, retries 20, start_period 10 s) |
| `postgres` | `pgvector/pgvector:0.8.7-pg16-trixie` | host port `127.0.0.1:${POSTGRES_PORT}` → container 5432; **default `POSTGRES_PORT=5433`** because a local Postgres already listens on 5432 on the owner's machine (T-01, decided 2026-10-05); volume; healthcheck `pg_isready` **[verified]**; `vector` 0.8.7 is available and `CREATE EXTENSION IF NOT EXISTS vector` works **[verified]**; credentials from `.env` |
| `topics` (job) | `apache/kafka:4.2.2` | `kafka-topics.sh --create --if-not-exists` for the 3 topics; `depends_on kafka: service_healthy`; run via `docker compose run --rm topics`; entrypoint `/bin/bash /create-topics.sh` with the script `infra/kafka/create-topics.sh` mounted read-only (a loop over `kafka-topics.sh --create --if-not-exists`). **[verified, T-01]**: creates 3 topics with 1 partition and replication 1; a second run exits 0 and leaves them unchanged; it still succeeds right after `restart kafka`. The "`.` and `_` metric-name collision" warning from Kafka is harmless (all names use dots only) |
| `migrate` (job) | built from `infra/migrations/Dockerfile` | `python:3.12-slim` + uv; installs `newsdock-db` with its `migrate` extra (alembic, psycopg) **[assumption: verified in the spike]**; env `DATABASE_URL`; command `alembic -c infra/migrations/alembic.ini upgrade head`; `depends_on postgres: service_healthy` |
| `<app>` ×6 | built from `apps/<app>/Dockerfile` | profile `apps`, build only in M0 |

`make down` stops containers and keeps volumes (decided 2026-10-05). `make up`: check `.env` → `docker compose up -d --wait kafka postgres` (**[verified, T-01]**: returned with both healthy after about 33 s wall time including container creation) → `make topics` → `make migrate`. One default network in M0; M1 splits `data` / `agent` (extension point). `--env-file ../.env`.

**`0001_baseline.py`:** `upgrade()` runs `CREATE EXTENSION IF NOT EXISTS vector`; `downgrade()` is a no-op (forward-only, DR-11). `env.py` imports `newsdock_db.config` for the URL and `newsdock_db.metadata` (empty in M0) as `target_metadata`. AC-11 check: after two `make migrate` runs, `select version_num from alembic_version` returns exactly `0001` and `pg_extension` lists `vector`.

**Findings from T-11 [verified]:** the async engine needs `sqlalchemy[asyncio]` (greenlet); `uv sync --frozen --package newsdock-db --extra migrate` works in the migration image, so alembic stays an optional extra of `newsdock-db` and is also in the root dev group for type checking; mypy needs the `pydantic.mypy` plugin for pydantic-settings classes; `make migrate` runs `docker compose run --rm --no-deps migrate` (Postgres must already be up; `make up` guarantees it), while `depends_on postgres: service_healthy` stays in the compose file for a full `docker compose up` in M1; `.env.example` is passed to compose for `build` and `down`, `.env` for `up`.

**`packages/db` (M0 content):** `config.py` (pydantic-settings, `DATABASE_URL`, driver `postgresql+psycopg`), `engine.py` (sync and async engine factories), `metadata.py` (empty `MetaData` with a naming convention), one smoke test. M1 adds tables here and the M1 design chooses Core versus mapped classes.

## 7. CI (`ci.yml`)

Triggers: `pull_request`, `push` to `main`. Jobs: `changes` (paths-filter; outputs per-app flags, `python`, `web` and `tooling` (= `Makefile` or `.github/workflows/**`, which reruns both check jobs); a shell step turns the app flags into the JSON matrix `apps`) → `check-python` (if `python` or `tooling`; also runs `make test-rules`), `check-web` (if `web` or `tooling`), `docs` (always: `make docs-check`), `build` (matrix of changed apps; all Python apps when `packages/core/**`, `pyproject.toml` or `uv.lock` changed), `ci-ok` (`needs` all, `if: always()`, fails on any failure/cancel). Steps use `make` targets so CI equals local. Filters: `python` = `apps/{ingester,processor,sink,api,agent}/**`, `packages/**`, `pyproject.toml`, `uv.lock`, `infra/scripts/**`; `web` = `apps/web/**`; per-app = `apps/<app>/**` plus the shared Python set.

## 8. Web scaffold (verified in T-02, 2026-10-05)

**Scaffold command** **[verified]**: `pnpm dlx create-next-app@16.3.8 web --ts --app --src-dir --eslint --use-pnpm --no-tailwind --no-react-compiler --import-alias "@/*" --yes` (run inside `apps/`). It generates Next 16.3.8, React 19.2.8, **TypeScript 5.9.3**, **ESLint 9.39.5**, `eslint-config-next` 16.3.8, `eslint.config.mjs`, `packageManager: pnpm@12.9.1`.

**Version pins, from trials** **[verified]**: keep `typescript` at `^5` and `eslint` at `^9`.
- TypeScript 7.0.2: `tsc --noEmit` and `next build` pass, but `typescript-eslint` 8.71.0 declares `typescript >=4.8.4 <6.1.0`, so `eslint` fails to load `eslint-config-next`.
- ESLint 10.12.0 also fails to load `eslint-config-next` 16.3.8. pnpm only prints a deprecation warning for ESLint 9.39.5; ignore it until `eslint-config-next` supports 10.

**Node pin** **[verified]**: `"devEngines": { "runtime": { "name": "node", "version": "24.x", "onFail": "download" } }` makes `pnpm install` add `node 24.21.0` as a dev dependency (lockfile: `runtime:24.21.0`); `pnpm exec node -v` and all `pnpm run` scripts use v24.21.0 although system Node is 26.9.0; `pnpm install --frozen-lockfile` stays a no-op.

**Test and format stack** **[verified]**: add dev dependencies `vitest@5.0.3`, `@testing-library/react@16.3.3`, `@testing-library/dom` (peer, 10.4.2), `jsdom` (30.1.2), `@vitejs/plugin-react` (6.1.1), `prettier@3.9.9`. Files: `vitest.config.ts` (react plugin, `environment: "jsdom"`, `include: ["src/**/*.test.{ts,tsx}"]`), `.prettierignore` (`.next`, `node_modules`, `pnpm-lock.yaml`). Scripts: `lint` = `eslint`, `format:check` = `prettier --check .`, `typecheck` = `tsc --noEmit`, `test` = `vitest run`. The scaffold's `next.config.ts` fails `prettier --check` until `prettier --write` runs once. A render smoke test (`render` + `getByRole`) passes.

**Standalone output** **[verified]**: `output: "standalone"` in `next.config.ts` makes `next build` write `.next/standalone/server.js` (+ minimal `node_modules`, 41 MB); `node .next/standalone/server.js` served HTTP 200. The image must also copy `.next/static` and `public/` next to it **[memory: documented Next behaviour]**.

**Generated files to know about** **[verified]**: `apps/web/pnpm-workspace.yaml` is a per-project pnpm 12 settings file (`allowBuilds: sharp: false, unrs-resolver: false`), not a multi-package workspace: no root pnpm workspace (DR-1) is unchanged. `apps/web/AGENTS.md` and `apps/web/CLAUDE.md` (`@AGENTS.md`) are generated by Next and re-added by `next dev`: allowed as an exception to DR-13 (decided 2026-10-05). Folders `features/`, `components/`, `lib/api/` are created with a `.gitkeep` and a README note (DR-12).

## 9. Full failure table

| Failure | Detection | Handling |
|---|---|---|
| Tool missing | `doctor` | list all missing, exit 1 |
| Docker daemon down | `docker info` | doctor message, `up`/`build` stop |
| `uv.lock` / `pnpm-lock.yaml` stale | `--locked` / frozen flag | fail with fix command |
| Layout or layering rule broken | `check_layout.py`, import-linter, ruff | exit 1 naming rule and path |
| Migration fails halfway | Alembic transactional DDL on Postgres **[memory]** | job exits non-zero; rerun after fixing |
| Kafka healthy flaps | healthcheck retries | `topics` retries via depends_on |
| Port 5433/29092 already used | compose error | README troubleshooting; `POSTGRES_PORT` (default 5433) configurable in `.env` |
| Image build fails | `docker compose build` | CI matrix names the app |
| CI path filter misses shared file | review | shared set listed in §7 |
| Secret committed | `.gitignore`, `.dockerignore`; scanning is backlog | `.env.example` placeholders only |

## 10. Security (M0)

Ports bound to `127.0.0.1`; `.env` git-ignored and excluded from images; compose passwords are local-dev placeholders; non-root image users; actions pinned by major tag (SHA pinning, Dependabot, secret and image scanning in `backlog.md`).

## 11. Spikes: first implementation task (de-risk before the rest)

Status after T-01 and T-02 (2026-10-05, both spikes done):

| # | Claim | Result |
|---|---|---|
| 1 | compose `up --wait` and `docker compose run --rm` jobs | **verified** (§6) |
| 2 | Kafka healthcheck command | **verified** (§6) |
| 3 | `uv sync --frozen --package` with a partial copy in Docker | **verified**, and simpler than designed: only the app's and its dependencies' manifests are needed (§5) |
| 4 | pnpm `devEngines.runtime` downloads Node 24 although Node 26 is installed | **verified** (§8) |
| 5 | Docker Desktop 4.93 on this macOS | **verified**: Docker Desktop 4.93.0, engine 29.8.1 linux/arm64, macOS 26.5.1 |
| 6 | TypeScript 7 with Next 16.3.8 | **contradicted**: tsc and build pass, but `typescript-eslint` rejects TS ≥ 6.1; pin TypeScript `^5` and ESLint `^9` (§8) |
| 7 | Both Kafka listeners reachable | **verified** (§6) |
| 8 | uv image tag for arm64 | **verified**: `ghcr.io/astral-sh/uv:0.12.23` has amd64 and arm64 |
| 9 | Host port 5432 free | **contradicted**: a local Postgres uses 127.0.0.1:5432; compose default is now 5433 (§6) |
