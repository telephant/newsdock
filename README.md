# newsdock

A shared "news dock" for AI agents: ingest the GDELT news feed once (clean, dedup, 7-day store) so any custom agent can plug in through an MCP server or REST. Kafka and Postgres run locally in Docker; there is no hosted demo.

**Status:** milestones M1–M3 are done. Live GDELT (GKG + Events + Mentions) flows through Kafka into Postgres; agents authenticate with API keys and read through MCP tools (`search_articles`, `semantic_search`, `list_new_articles`, …) or REST, with server-side cursors and SSE push for saved filters; humans sign up and use the Next.js UI. Semantic search runs on pgvector + Ollama, article bodies are fetched politely by a dedicated extractor, and an independent digest agent ([`agents/whathappen`](agents/whathappen/)) writes an hourly top-stories digest. See the [roadmap](docs/roadmap.md).

## Architecture

```
GDELT 15-min slots (GKG + Events + Mentions) → ingester → Kafka gkg.raw
    → processor → gkg.clean / events.clean / mentions.clean (bad rows → gkg.dlq)
    → sink → Postgres (7-day retention)
Postgres ← embedder (titles → Ollama on the host → pgvector; body passages opt-in)
Postgres ← extractor (the only component on the open web: polite, SSRF-guarded
                      page fetch → cleaned text + passages, 7 days)
Postgres → api (MCP /mcp + REST /api/*) → agents (keys, cursors, SSE push) + web UI (:3000)
```

Component map and diagrams: [design](docs/specs/mvp/design.md), [diagrams](docs/specs/mvp/diagrams/index.html).

### Honest notes

- **Kafka is here for learning and decoupling, not throughput.** The GKG feed is ~30–50k rows/day; a single Postgres would cope easily.
- **Downtime leaves slot gaps.** Only slots seen in `lastupdate.txt` while the ingester runs are fetched; there is no history backfill (backlog). A listed-but-404 slot is retried up to 4 times, then marked `failed`.
- **Data: [GDELT Project](https://www.gdeltproject.org/)** — free open data; this project polls the 15-minute index no faster than every 15 minutes. Article pages are fetched only by the extractor: robots.txt honoured, an honest user agent, one request per site at a time, text kept 7 days.

## Prerequisites (macOS on Apple silicon)

Install these once; the repo documents nothing else as manual:

| Tool | Install | Notes |
|---|---|---|
| Docker Desktop | `brew install --cask docker-desktop` | Start it and wait until it is running |
| uv | `brew install uv` | Provisions Python 3.12 automatically |
| pnpm | `brew install pnpm` | Provisions Node 24 LTS automatically (`devEngines` in `apps/web/package.json`) |
| Ollama | `brew install --cask ollama-app` | Then `ollama pull llama3.2:3b` (the demo agent) and `ollama pull nomic-embed-text` (the embedder and `semantic_search`) |

## Quick start

```bash
make doctor          # check the tools above
make setup           # install Python (uv) and web (pnpm) dependencies from the lockfiles
make check           # lint, format, types, import rules, layout, tests, docs
make build           # build the app images and the migration image
cp .env.example .env # local settings (git-ignored; placeholders only)
make up              # Kafka and Postgres healthy, topics created, migrations applied
docker compose --env-file .env -f infra/compose.yaml --profile apps up -d --wait
                     # start all services (pipeline, embedder, extractor, api :8000, web :3000)
make down            # stop everything (data volumes are kept)
```

## Commands

`make help` lists everything; the daily ones:

| Command | What it does |
|---|---|
| `make doctor` / `make setup` | Verify the tools / install dependencies from the lockfiles |
| `make check` | `check-python` + `check-web` + `docs-check` (lint, types, import rules, layout, tests) |
| `make test APP=<name>` | Tests of one app: `ingester processor sink embedder extractor api agent web` |
| `make test-infra [SCENE=<name>]` | Docker tests, scoped: `db kafka sink api embedder extractor pipeline e2e stack images`. Needs Docker and ports 5433/29092 free |
| `make build [APP=<name>]` | Build images (`newsdock-<app>:dev`, `newsdock-migrate:dev`) |
| `make up` / `make down` | Start (and wait for) Kafka and Postgres, create topics, migrate / stop |
| `make agent-create NAME=<name>` | Register an agent and print its API key once (needs `NEWSDOCK_ADMIN_TOKEN` in `.env` and the api up) |

## Logins, agents and push

The short version; roles, rate limits, password reset by email, key routes and SSE semantics are in the **[operations guide](docs/operations.md)**.

- Open **http://127.0.0.1:3000** and *Sign up*: the first account becomes the `owner`, later ones `viewer`s. Reads (`GET /api/articles*`) need a login or an agent key.
- `make agent-create NAME=<name>` prints an agent's API key once (or create agents in the UI at `/admin/agents`); MCP clients send `Authorization: Bearer <key>` to `/mcp`. The server keeps each agent's cursor (`ack_cursor`) and rate limit.
- Agents can save filters (`POST /api/subscriptions`) and stream matching new articles over SSE instead of polling.

## Configuration

All non-secret settings live in one file, [`infra/config/newsdock.yaml`](infra/config/newsdock.yaml): a `common:` section every service inherits, one section per service. Env vars override any key (**env > file > built-in defaults**), and the file's values equal the defaults, so an empty file changes nothing. Nested keys flatten with `_` into the env name (`sink.retention_days` ↔ `NEWSDOCK_RETENTION_DAYS`). Secrets (`DATABASE_URL`, passwords) stay in `.env` — a secret-looking key in the file stops the service at startup — and host ports (`API_PORT`, `WEB_PORT`, `POSTGRES_PORT`) are `.env` values because compose cannot read the YAML. Details: [ADR-0013](docs/adr/0013-layered-config-package-and-yaml.md).

## Layout

```
apps/{ingester,processor,sink,embedder,extractor,api,agent}   Python services, one deployable each
apps/web                                   Next.js + TypeScript UI
agents/whathappen                          independent digest agent (own compose; a client of the platform)
packages/{core,db,config,embedding}        shared Python packages
infra/                                     compose.yaml, config/newsdock.yaml, migrations/ (Alembic), scripts/
docs/                                      roadmap, specs, ADRs, research, operations guide
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

The first checks; the longer tail (Ollama outages, silent streams, rejected keys, body backlogs) is in the [operations guide](docs/operations.md#troubleshooting).

- **`MISSING <tool>` from `make doctor`:** run the install command it prints.
- **Docker daemon not reachable:** start Docker Desktop and wait until it is running.
- **`make up` says `missing .env`:** run `cp .env.example .env`.
- **Port already in use:** Postgres defaults to host port 5433 (a local Postgres often owns 5432); change `POSTGRES_PORT` in `.env`. Kafka uses 29092.
- **`ollama list` shows no model:** `ollama pull llama3.2:3b` and `ollama pull nomic-embed-text`.
- Only macOS on Apple silicon is documented and tested.
