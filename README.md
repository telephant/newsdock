# newsdock

A shared "news dock" for AI agents: ingest the GDELT GKG news feed once (clean, dedup, 7-day store) so any custom agent can plug in through an MCP server or REST. Kafka and Postgres run locally in Docker; there is no hosted demo.

**Status:** M1 `mvp` implemented: live GDELT GKG → Kafka → processor → Postgres (7-day retention) → MCP + REST → demo financial-relevance agent (Ollama) → Next.js UI. See the [roadmap](docs/roadmap.md).

## Architecture

```
GDELT GKG (15-min slots) → ingester → Kafka gkg.raw → processor → gkg.clean / gkg.dlq
                                                            → sink → Postgres (7 days)
Postgres → api (MCP /mcp + REST /api/*) → demo agent (Ollama, host) and web UI (:3000)
```

Component map and diagrams: [design](docs/specs/mvp/design.md), [diagrams](docs/specs/mvp/diagrams/index.html).

### Honest notes

- **Kafka is here for learning and decoupling, not throughput.** The GKG feed is ~30–50k rows/day; a single Postgres would cope easily.
- **Downtime leaves slot gaps.** Only slots seen in `lastupdate.txt` while the ingester runs are fetched; there is no history backfill (backlog). A listed-but-404 slot is retried up to 4 times, then marked `failed`.
- **Data: [GDELT Project](https://www.gdeltproject.org/)** — free open data; this project polls the 15-minute index no faster than every 15 minutes and stores no article bodies.

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
| `docker compose --env-file .env -f infra/compose.yaml --profile apps up -d --wait` | Start all 8 services (pipeline, api :8000, web :3000) |
| `make topics`, `make migrate` | Create the Kafka topics (configured names), apply Alembic migrations (both idempotent) |
| `make config-python` | Check `infra/config/newsdock.yaml` and that no tunable literal crept back into code |
| `make test-rules` | Prove each enforced rule fails when violated |
| `make test-infra [SCENE=<name>]` | Docker tests; scenes scope the run to what you're working on: `db`, `kafka`, `sink`, `api`, `pipeline`, `e2e`, `stack`, `images` (no scene = everything, ~4 min warm). Needs Docker and ports 5433/29092 free |
| `make docs-check` | README sections and relative links |

## Configuration

All non-secret settings live in one file, [`infra/config/newsdock.yaml`](infra/config/newsdock.yaml): a `common:` section that every service inherits, and one section per service (`ingester`, `processor`, `sink`, `api`, `agent`, `web`). Docker env vars override any key (**env > file > built-in defaults**), and the file's values equal the defaults, so an empty file changes nothing. Nested keys flatten with `_` into the env name, e.g. `sink.retention_days` ↔ `NEWSDOCK_RETENTION_DAYS`, `common.kafka.topics.clean` ↔ `NEWSDOCK_KAFKA_TOPICS_CLEAN` (agent: prefix `NEWSDOCK_AGENT_`).

- **Change a value:** edit the file and `docker compose ... up -d <service>`, or set the env var in `.env` / the compose `environment:`.
- **Point a service at another file:** `NEWSDOCK_CONFIG_FILE=/path/to/newsdock.yaml` (compose mounts `infra/config` read-only at `/etc/newsdock`).
- **Secrets** (`DATABASE_URL`, `POSTGRES_PASSWORD`) stay in `.env`; a secret-looking key in the file stops the service at startup.
- **Host ports** (`API_PORT`, `WEB_PORT`, `POSTGRES_PORT`) are `.env` values because compose cannot read the YAML.
- Details: [ADR-0013](docs/adr/0013-layered-config-package-and-yaml.md), [spec](docs/specs/externalize-config/spec.md).

## Layout

```
apps/{ingester,processor,sink,api,agent}   Python services, one deployable each
apps/web                                   Next.js + TypeScript UI
packages/core, packages/db, packages/config   shared Python packages (config = layered settings loader)
infra/                                     compose.yaml, config/newsdock.yaml, migrations/ (Alembic), scripts/
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
- **`ollama list` shows no model:** run `ollama pull llama3.2:3b` (the demo agent's model, chosen in the M1 spike).
- **Agent logs `batch failed`:** usually Ollama is not running on the host (`ollama list` must answer); the agent retries with its cursor unchanged.
- Only macOS on Apple silicon is documented and tested.
