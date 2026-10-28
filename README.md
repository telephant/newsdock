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
| `make agent-create NAME=<name>` | Register an agent and print its API key once (needs `NEWSDOCK_ADMIN_TOKEN` in `.env` and the api up) |
| `make user-reset-password EMAIL=<email>` | Owner recovery: set a user's password (asks twice, never echoed; ends that user's sessions and lifts a login lockout; needs `NEWSDOCK_ADMIN_TOKEN` in `.env` and the api up). Only the admin token can do this; an admin or owner session cannot |
| `make config-python` | Check `infra/config/newsdock.yaml` and that no tunable literal crept back into code |
| `make test-rules` | Prove each enforced rule fails when violated |
| `make test-infra [SCENE=<name>]` | Docker tests; scenes scope the run to what you're working on: `db`, `kafka`, `sink`, `api`, `pipeline`, `e2e`, `stack`, `images` (no scene = everything, ~4 min warm). Needs Docker and ports 5433/29092 free |
| `make docs-check` | README sections and relative links |

## Accounts and login (M2)

The UI needs a login. Open **http://127.0.0.1:3000** (the compose default; `http://localhost:3000` is redirected there, because the login cookie only works when page and API share a hostname). Use *Sign up*: **the first account becomes the `owner`**, every later one a `viewer`.

| Role | May |
|---|---|
| `viewer` | read the feed and articles, watch `/live` |
| `admin` | also manage agents and keys, and view or delete subscriptions (`/admin/agents`, `/admin/subscriptions`) |
| `owner` | also change roles and delete users (`/admin/users`); the last owner can never be demoted or deleted |

- **Sign-up is open by default.** Anyone who can reach the web port can register a `viewer` account, which can read articles and create its own agents and API keys. Close it with `api.auth_signup_open: false` in `infra/config/newsdock.yaml` (then create accounts by temporarily re-opening it); there is no email verification, invite or CAPTCHA in this milestone.
- **Sign-ups and agents are rate limited** (all in `infra/config/newsdock.yaml`, `0` turns a limit off): `auth_signup_max_per_address` (5) counted sign-ups per client address and `auth_signup_max_total` (50) in total per `auth_signup_window_minutes` (60) answer HTTP 429 with `Retry-After`; `agents_max_per_user` (10) agents per non-owner user answers 409 `too_many_agents` (the `owner` role and the admin token are exempt, disabled agents count). The counters live in memory in the single API process and reset on restart. The address is the TCP peer address, and `X-Forwarded-For` is ignored because a client can forge it; behind Docker Desktop every browser on the host arrives as the Docker gateway address, so locally the per-address limit (5 per hour) is in effect the total: raise `auth_signup_max_per_address` if you create more accounts than that on one machine.
- **Locked-out owner:** `make user-reset-password EMAIL=<email>` asks for a new password twice (not echoed), ends that user's sessions and lifts a login lockout. It needs `NEWSDOCK_ADMIN_TOKEN` in `.env` and the api up; a session cannot do this, only the token.
- **Reads are no longer open:** `GET /api/articles*` accepts a browser session or an agent key. `api.auth_required: false` (with `web.login_required: false`) switches login off for local experiments.
- Passwords are hashed with argon2id; sessions are server-side (12 h idle, 7 days absolute, both in the config file); five wrong passwords for one account lock it for 15 minutes.

## Agents and API keys (M2)

MCP (`/mcp`) needs an agent API key; `api.auth_required` in the config file (default `true`) turns that off for local experiments. Agents are registered by a signed-in user (in the UI at `/admin/agents`) or by the operator with the admin token below. **Each agent belongs to the user who created it:** a user sees and manages only their own agents, keys and subscriptions, and the `owner` role sees all of them. Agents made with the admin token (`make agent-create`), agents from before ownership existed (for example `demo-financial`) and agents whose creator was deleted have **no owner**: they keep working, but only the `owner` role (in the UI) and the admin token can manage them.

1. For the command line, put a long random `NEWSDOCK_ADMIN_TOKEN` in `.env` and start the stack (while it is empty the token opens nothing; signed-in users can still manage their own agents in the UI).
2. `make agent-create NAME=demo-financial` prints the agent's key **once**; only a hash is stored. More routes: `GET /api/admin/agents`, `POST /api/admin/agents/{id}/keys`, `DELETE /api/admin/agents/{id}/keys/{key_id}`, `POST /api/admin/agents/{id}/disable|enable` (all with `Authorization: Bearer <admin token>`, which reaches every agent, or a logged-in session, which reaches the caller's own agents, or every agent for the `owner` role; another user's agent answers 404).
3. Put the key in `.env` as `NEWSDOCK_AGENT_API_KEY` and restart the agent. Any MCP client sends `Authorization: Bearer <key>`.

The server keeps each agent's position: `list_new_articles` without a cursor resumes after the last `ack_cursor` the agent sent (call it after finishing a batch), and each agent is limited to `api.rate_limit_per_minute` requests (HTTP 429 with `Retry-After`). **Reading needs a login or a key** (ui-login closed the old open-reads risk): `GET /api/articles*` accepts a browser session or an agent key.

## Subscriptions and push streams (M2)

An authenticated agent can save filters and have matching new articles pushed to it over Server-Sent Events, instead of polling `list_new_articles`.

```bash
KEY=ndk_...   # from `make agent-create NAME=<name>`
# the body is the filter: theme (exact, or a prefix like ECON_*), domain, title text; all optional
curl -sS -X POST http://127.0.0.1:8000/api/subscriptions -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{"theme":"ECON_*","domain":"example.com"}'
curl -N -H "Authorization: Bearer $KEY" http://127.0.0.1:8000/api/subscriptions/<id>/stream
curl -N -H "Authorization: Bearer $KEY" -H "Last-Event-ID: <last id>" .../stream   # resume
```

Each event is `id: <cursor>`, `event: article`, `data: <article summary JSON>`; idle streams get `: ping` comment lines every `api.sse_keepalive_seconds`. Delivery is at-least-once: a reconnect with `Last-Event-ID` resumes strictly after that article (duplicates are possible, dedupe by `article_id`). Without `Last-Event-ID` a stream starts after the agent's acknowledged cursor, or from the last hour for a new agent; streaming never moves that cursor, only `ack_cursor` does. Other routes: `GET /api/subscriptions` (own), `DELETE /api/subscriptions/{id}`; limits `api.subscriptions_max_per_agent` (409), `api.sse_max_streams_per_agent` (429); `GET /api/admin/subscriptions` lists everyone's (admin token). A revoked key or disabled agent ends its open streams within one keep-alive interval. New articles reach streams through a Postgres `NOTIFY` raised by a trigger on `articles` ([ADR-0018](docs/adr/0018-sse-streams-wake-on-listen-notify.md)).

## Configuration

All non-secret settings live in one file, [`infra/config/newsdock.yaml`](infra/config/newsdock.yaml): a `common:` section that every service inherits, and one section per service (`ingester`, `processor`, `sink`, `api`, `agent`, `web`). Docker env vars override any key (**env > file > built-in defaults**), and the file's values equal the defaults, so an empty file changes nothing. Nested keys flatten with `_` into the env name, e.g. `sink.retention_days` ↔ `NEWSDOCK_RETENTION_DAYS`, `common.kafka.topics.clean` ↔ `NEWSDOCK_KAFKA_TOPICS_CLEAN` (agent: prefix `NEWSDOCK_AGENT_`).

- **Change a value:** edit the file and `docker compose ... up -d <service>`, or set the env var in `.env` / the compose `environment:`.
- **Point a service at another file:** `NEWSDOCK_CONFIG_FILE=/path/to/newsdock.yaml` (compose mounts `infra/config` read-only at `/etc/newsdock`).
- **Login settings** (`api.auth_*`, `api.cors_*`, `web.session_cookie`, `web.login_required`) are in the same file; `web.session_cookie` must equal `api.auth_cookie_name`.
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
- **Agent logs `batch failed`:** usually Ollama is not running on the host (`ollama list` must answer); the agent retries and, because it only acks after a finished batch, re-reads the same batch.
- **A stream stays silent:** check the subscription's filter (`GET /api/subscriptions`) and that new articles are arriving (GDELT slots land every ~15 min); `: ping` lines mean the connection is healthy. A `429` on connect means the agent already has `api.sse_max_streams_per_agent` open streams.
- **Agent logs `the API rejected this agent's key (HTTP 401)`:** `NEWSDOCK_AGENT_API_KEY` is empty, wrong or revoked; issue a new key with `make agent-create` (or set `api.auth_required: false` for local experiments).
- Only macOS on Apple silicon is documented and tested.
