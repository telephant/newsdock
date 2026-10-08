# newsdock

News "dock" for AI agents: ingests the GDELT GKG feed every 15 min, cleans it with a Python Kafka processor, keeps 7 days in Postgres, and serves it to agents through an MCP server and REST. Local docker-compose only. Milestone 1 (MVP) is a walking skeleton.

## Status
- Stage: M0 `foundation` and M1 `mvp` both done and verified (M1: pass with follow-ups, 2026-10-05 — all 15 ACs, agent F1 0.83, live end-to-end run; see `docs/specs/mvp/verify.md`). M2a `dedup-syndication` committed (verification pending). In progress: M2b `externalize-config` (one YAML config file + env overrides, spec `docs/specs/externalize-config/`). Next milestone after: M2 (push subscriptions, agent registry/auth) via `/spec-init`.
- Roadmap: `docs/roadmap.md` (current milestone: M2b).
- Source of truth, in this order: `docs/specs/mvp/spec.md` (ACs) → `docs/specs/mvp/design.md` → `docs/adr/` → `docs/specs/mvp/design-detail.md`.
- Real GDELT evidence and a sample row: `docs/research.md`. Check it before assuming anything about the data.
- Open items: `docs/specs/mvp/backlog.md` ("Design TODOs").

## Repo layout (monorepo, Python + TypeScript in one git repo)
- `apps/<service>/` one deployable per folder: `ingester`, `processor`, `sink`, `api`, `agent` (Python) and `web` (Next.js + TS). Each app owns its dependency file and Dockerfile.
- `packages/core/` shared pure Python code (GKG parsing, URL normalisation, models, contracts); `packages/db/` SQLAlchemy engine, config and metadata; `packages/config/` the layered config loader (`newsdock_config`, ADR-0013). Apps may import `packages/*`, never another app.
- `infra/` docker-compose, `infra/config/newsdock.yaml` (the one config file), Alembic migrations, check scripts. `docs/` specs and ADRs.
- The only link between Python and TS is the REST/OpenAPI contract; generate the UI's types from it instead of hand-writing them.
- Python: one `uv` workspace at the root (planned); web: its own `package.json` in `apps/web`. CI jobs run only for the apps whose files changed.

## Directory rules (foundation spec §6, DR-1…DR-13; enforced by `make check` once M0 builds it)
- Repo root: only `apps/`, `packages/`, `infra/`, `docs/`, `.github/` and root tooling files. New app or top-level folder needs an ADR.
- Python app: `pyproject.toml`, `Dockerfile`, `README.md`, `src/newsdock_<app>/`, `tests/`. Code only under `src/`, tests only under `tests/` (`unit/` mirrors `src/`, `integration/` marked).
- Inside every Python app: `__main__.py` wires only; `domain/` is pure logic (stdlib, pydantic, `newsdock_core` only); `adapters/` holds all I/O. Adapters import domain, never the reverse.
- Apps import `packages/*` only, never another app. `newsdock_core` imports no app and no I/O library. Shared contracts live once in `newsdock_core.contracts`; GDELT fixtures only in `packages/core/tests/fixtures/`.
- Env is read only in `config.py`. SQL and query building only in `adapters/` and Alembic migrations (`infra/migrations/versions/NNNN_<name>.py`), always parameterized. DB access is SQLAlchemy 2 via the shared package `packages/db` (`newsdock_db`); `domain/` and `newsdock_core` never import it.
- Web `src/`: `app/` thin routes, `features/<name>/` feature code, `components/` shared UI without data fetching, `lib/api/` generated client (never hand-edited).

## Workflow
- A local pass is not CI: the first GitHub run found a non-existent action tag (`setup-uv@v10`), a test PATH that hid a real `/usr/bin/docker`, and a job without pnpm. After touching `.github/`, push and read the run (`gh run watch`, `gh run view --log-failed`).
- Work follows the spec pipeline: `/spec-init` → `/spec-design` → `/spec-plan` → `/spec-implement` → `/spec-verify`, one folder per feature under `docs/specs/<name>/`.
- Implement one task at a time from `docs/specs/mvp/tasks/T-NN.md`, test first. Use only the context that task names.
- Every acceptance criterion `AC-n` in `spec.md` must end up covered by a test or a manual check listed in `tests.md`.
- When a doc changes, update every file that repeats the fact (ids, topic names, tool names, statuses) in the same edit, and note stale downstream files.
- Changing a decided item (`D-n` in the spec, an Accepted ADR) needs the user's approval; record the change in the spec/ADR with the date.

## Architecture (ids are used in all docs)
- C-1 Ingester → C-2 Kafka (default topics `gkg.raw`, `gkg.clean`, `gkg.dlq`; names are config, ADR-0013) → C-3 Python processor (stateless: parse, validate, route) → C-4 sink + retention → C-5 Postgres 16 + pgvector (unused in MVP).
- C-6 API: one FastAPI process serving MCP (streamable HTTP, `/mcp`) and REST (`/api/*`) over one service layer.
- C-7 demo agent (MCP client + Ollama on host), C-8 Next.js UI (REST only).
- Flink was deliberately dropped (ADR-0001). Do not reintroduce stateful stream engines in the MVP.

## Fixed names (do not rename without updating all docs)
- MCP tools: `search_articles`, `get_article`, `list_new_articles`, `submit_analysis`.
- Public article id is `url_hash` (sha256 of the normalized URL). `seq` (bigserial) drives the cursor, never expose it raw: the cursor is opaque base64.
- Tables: `articles` (canonicals; `story_key` NULL = pre-M2a row), `analyses`, `ingest_slot`, `article_sources` (copies; PK `url_hash`, FK → canonical, CASCADE). Slot format: `YYYYMMDDHHMMSS`.
- Dead-letter reasons: `missing_url`, `missing_title`, `bad_column_count`, `bad_field`.
- Agent score payload: `{relevant, score (0–1), reason}`; `submit_analysis` accepts any JSON object.
- Story grouping (M2a): key = `newsdock_core.stories.story_key` (normalized title, fixpoint suffix-strip) within ± `NEWSDOCK_STORY_WINDOW_HOURS` (48); API fields `source_count` and `sources[]`.

## GDELT rules (verified in `docs/research.md`)
- Follow redirects; `http://` URLs in the index redirect to `https://`.
- A slot can be listed yet return 404 or an empty body. Treat 404, empty body or md5 mismatch as "retry later" (slot stays `pending`, max 4 attempts), never as an error or as data.
- Poll interval is configurable but never below 900 s.
- GKG rows are 27 tab-separated columns with no header. The title is inside column 27 (`<PAGE_TITLE>`), not its own column. Empty themes, persons and orgs are normal (do not dead-letter them); only a missing URL or title is a bad row.
- There is no article body in GKG. Do not scrape article pages in the MVP.

## Code conventions
- Backend: Python 3.12+, fully typed, async where I/O bound, tests with pytest. Frontend: Next.js with TypeScript.
- All consumers are at-least-once with manual offset commits; all writes must be idempotent (`ON CONFLICT (url_hash) DO NOTHING`).
- SQL is always parameterized. Render agent payloads in the UI as escaped text, never HTML.
- Secrets live in `.env` (git-ignored). Never commit credentials or put them in docs.
- The demo agent must have no database credentials and no route to Postgres or Kafka; it reaches data only through the MCP server (AC-13).

## Configuration (ADR-0013, spec `externalize-config`)
- Every tunable lives in `infra/config/newsdock.yaml`: a `common:` parent inherited by the `ingester`, `processor`, `sink`, `api`, `agent`, `web` sections. Precedence: env > file > code defaults. Nested keys flatten with `_` to the setting name (`kafka.topics.clean` → `kafka_topics_clean` → env `NEWSDOCK_KAFKA_TOPICS_CLEAN`); agent env prefix is `NEWSDOCK_AGENT_`.
- Secrets (`DATABASE_URL`, passwords) stay in `.env`/the environment; the loader rejects secret-looking keys in the file. The file holds the defaults, so an empty file changes nothing.
- A new setting = a field on that app's `Settings` (extends `newsdock_config.LayeredSettings`) with the old literal as default, plus its row in the file if you want it visible. `make config-python` fails on unknown keys, values that differ from defaults, and tunable literals (topic names, retry/retention constants) reintroduced in code. Manual offset commits and `follow_redirects=True` stay in code (invariants, not tunables).
- Healthchecks are app code (`newsdock_<app>.adapters.healthcheck`); the worker writes its own allowed heartbeat age into `heartbeat_file`. Host ports come from `.env` (`API_PORT`, `WEB_PORT`, `POSTGRES_PORT`); container ports are fixed. The web app reads its `web:` section at server start (no rebuild to change the API base).

## Docs conventions
- Tag factual claims in specs/designs as **[verified]**, **[memory]** or **[assumption]**; only tag **[verified]** after checking this session.
- Keep `design.md` ≤ ~150 lines; detail goes in `design-detail.md`. Each design diagram has ≤ ~12 nodes and a "Check" box.
- ADRs live in `docs/adr/NNNN-<decision>.md` with a Status line; never treat a Proposed ADR as decided.

## Commands (run from the repo root; `make help` lists them)
- `make doctor` check tools; `make setup` install from lockfiles; `make check` everything (`check-python`, `check-web`, `docs-check`).
- `make test APP=<ingester|processor|sink|api|agent|web>` one app's tests; `make test-rules` proves each enforced rule fails when violated (`test-rules-python` skips the pnpm-dependent ones; CI uses it); `make test-infra [SCENE=<db|kafka|sink|api|pipeline|e2e|stack|images>]` Docker tests, scoped to one scene or all (needs Docker, ports 5433 and 29092 free, no `.env` surprises: it backs up and restores your own).
- `make build [APP=<name>]` images (`newsdock-<app>:dev`, `newsdock-migrate:dev`); `cp .env.example .env` then `make up` / `make down`; `make topics`, `make migrate` are idempotent.
- Raw compose needs the env file: `docker compose --env-file .env -f infra/compose.yaml ps` (compose looks for `.env` next to the compose file otherwise).
- Python: `uv run ...` (never `pip`); one workspace, `uv sync --all-packages --locked`. Web: `pnpm --dir apps/web run <script>`; Node 24 comes from pnpm, not the system.
- Quality tools: ruff (lint, format, `TID251` bans `os.environ`/`os.getenv` outside `config.py`), mypy strict with the pydantic plugin, import-linter contracts in `pyproject.toml`, `infra/scripts/check_layout.py`, `infra/scripts/check_docs.py`, `infra/scripts/check_config.py` (`make config-python`).

## Environment notes
- Machine: macOS arm64. Docker Desktop 4.93, uv, pnpm and Ollama are installed; Ollama has `llama3.2:1b` pulled (enough for AC-2; the M1 spike picks the demo-agent model).
- A local Postgres already listens on 5432, so compose publishes Postgres on 5433 (`POSTGRES_PORT`).
- Spike findings and verified versions: `docs/specs/foundation/design-detail.md` §5, §6, §8, §11.

<!-- Maintainer note: keep this file under 200 lines; move topic-specific rules to .claude/rules/ with `paths` frontmatter once code exists. -->
