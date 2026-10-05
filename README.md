# newsdock

A shared "news dock" for AI agents: ingest the GDELT GKG news feed once (clean, dedup, 7-day store) so any custom agent can plug in through an MCP server or REST. Kafka and Postgres run locally in Docker; there is no hosted demo.

**Status:** milestone M0 `foundation` (monorepo, tooling, CI, docs) is implemented. The data pipeline, API, agent and UI arrive in M1; see the [roadmap](docs/roadmap.md).

## Prerequisites (macOS on Apple silicon)

Install these once; the repo documents nothing else as manual:

| Tool | Install | Notes |
|---|---|---|
| Docker Desktop | `brew install --cask docker-desktop` | Start it and wait until it is running |
| uv | `brew install uv` | Provisions Python 3.12 automatically |
| pnpm | `brew install pnpm` | Provisions Node 24 LTS automatically (`devEngines` in `apps/web/package.json`) |
| Ollama | `brew install --cask ollama-app` | Then `ollama pull <any small model>` (used by the M1 demo agent) |

## Quick start

```bash
make doctor          # check the tools above
make setup           # install Python (uv) and web (pnpm) dependencies from the lockfiles
make check           # lint, format, types, import rules, layout, tests, docs
make build           # build the six app images and the migration image
cp .env.example .env # local settings (git-ignored; placeholders only)
make up              # Kafka and Postgres healthy, topics created, migrations applied
make down            # stop everything (data volumes are kept)
```

## Commands

| Command | What it does |
|---|---|
| `make doctor` | Verify Docker, Compose, uv, pnpm, Ollama; print resolved Python and Node |
| `make setup` | `setup-python` (`uv sync --all-packages --locked`) and `setup-web` (`pnpm install --frozen-lockfile`) |
| `make check` | `check-python` + `check-web` + `docs-check` |
| `make test APP=<name>` | Tests of one app: `ingester processor sink api agent web` |
| `make build [APP=<name>]` | Build images (`newsdock-<app>:dev`, `newsdock-migrate:dev`); no `.env` needed |
| `make up` / `make down` | Start (and wait for) Kafka and Postgres, create topics, migrate / stop |
| `make topics`, `make migrate` | Create the Kafka topics, apply Alembic migrations (both idempotent) |
| `make test-rules` | Prove each enforced rule fails when violated |
| `make test-infra` | Docker-based tests (images and stack); needs Docker running and ports 5433 and 29092 free |
| `make docs-check` | README sections and relative links |

## Layout

```
apps/{ingester,processor,sink,api,agent}   Python services, one deployable each
apps/web                                   Next.js + TypeScript UI
packages/core, packages/db                 shared Python packages
infra/                                     compose.yaml, kafka/, migrations/ (Alembic), scripts/
docs/                                      roadmap, specs, ADRs, research
```

The directory and layering rules (`domain/` pure, `adapters/` for I/O, apps never import each other) are enforced by `make check`; see [ADR-0006](docs/adr/0006-directory-layout-and-layering.md) and the rules DR-1 to DR-13 in the [foundation spec](docs/specs/foundation/spec.md). Everything else is in the [documentation index](docs/README.md).

## Versions (verified 2026-10-05)

| Component | Version |
|---|---|
| Docker Desktop (tested) | 4.93.0, engine 29.8.1 |
| uv / Python | 0.12.23 / 3.12 (provisioned by uv) |
| pnpm / Node | 12.9.1 / 24 LTS (provisioned by pnpm; 24.21.0 at the time of writing) |
| Next.js / React / TypeScript / ESLint | 16.3.8 / 19.2.8 / ^5 / ^9 |
| Kafka image | `apache/kafka:4.2.2` (KRaft, single broker) |
| Postgres image | `pgvector/pgvector:0.8.7-pg16-trixie` |
| SQLAlchemy / Alembic | 2.1.3 / 1.20.0 |

## Troubleshooting

- **`MISSING <tool>` from `make doctor`:** run the install command it prints.
- **Docker daemon not reachable:** start Docker Desktop and wait until it is running.
- **`make up` says `missing .env`:** run `cp .env.example .env`.
- **Raw `docker compose` complains about missing variables:** pass the env file, e.g. `docker compose --env-file .env -f infra/compose.yaml ps` (compose looks for `.env` next to the compose file otherwise).
- **Port already in use:** Postgres defaults to host port 5433 (a local Postgres often owns 5432); change `POSTGRES_PORT` in `.env`. Kafka uses 29092.
- **`ollama list` shows no model:** run `ollama pull <model>`; only `make doctor` warns about it in M0.
- Only macOS on Apple silicon is documented and tested.
