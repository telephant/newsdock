# newsdock

News "dock" for AI agents: ingests the GDELT GKG feed every 15 min, cleans it with a Python Kafka processor, keeps 7 days in Postgres, and serves it to agents through an MCP server and REST. Local docker-compose only. Milestone 1 (MVP) is a walking skeleton.

## Status
- Stage: M0 `foundation` implemented (tasks T-00…T-14 done), next `/spec-verify foundation`. M1 `mvp` design is approved; update its docs for M0 decisions (`packages/db`, SQLAlchemy layer, tooling) in `/spec-design mvp`, then `/spec-plan mvp`. Only skeleton code exists (apps print their name; no domain logic yet).
- Roadmap: `docs/roadmap.md` (current milestone: M0).
- Source of truth, in this order: `docs/specs/mvp/spec.md` (ACs) → `docs/specs/mvp/design.md` → `docs/adr/` → `docs/specs/mvp/design-detail.md`.
- Real GDELT evidence and a sample row: `docs/research.md`. Check it before assuming anything about the data.
- Open items: `docs/specs/mvp/backlog.md` ("Design TODOs").

## Repo layout (monorepo, Python + TypeScript in one git repo)
- `apps/<service>/` one deployable per folder: `ingester`, `processor`, `sink`, `api`, `agent` (Python) and `web` (Next.js + TS). Each app owns its dependency file and Dockerfile.
- `packages/core/` shared pure Python code (GKG parsing, URL normalisation, models, contracts); `packages/db/` SQLAlchemy engine, config and metadata. Apps may import `packages/*`, never another app.
- `infra/` docker-compose, Alembic migrations, Kafka topic setup, check scripts. `docs/` specs and ADRs.
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
- Work follows the spec pipeline: `/spec-init` → `/spec-design` → `/spec-plan` → `/spec-implement` → `/spec-verify`, one folder per feature under `docs/specs/<name>/`.
- Implement one task at a time from `docs/specs/mvp/tasks/T-NN.md`, test first. Use only the context that task names.
- Every acceptance criterion `AC-n` in `spec.md` must end up covered by a test or a manual check listed in `tests.md`.
- When a doc changes, update every file that repeats the fact (ids, topic names, tool names, statuses) in the same edit, and note stale downstream files.
- Changing a decided item (`D-n` in the spec, an Accepted ADR) needs the user's approval; record the change in the spec/ADR with the date.

## Architecture (ids are used in all docs)
- C-1 Ingester → C-2 Kafka (`gkg.raw`, `gkg.clean`, `gkg.dlq`) → C-3 Python processor (stateless: parse, validate, route) → C-4 sink + retention → C-5 Postgres 16 + pgvector (unused in MVP).
- C-6 API: one FastAPI process serving MCP (streamable HTTP, `/mcp`) and REST (`/api/*`) over one service layer.
- C-7 demo agent (MCP client + Ollama on host), C-8 Next.js UI (REST only).
- Flink was deliberately dropped (ADR-0001). Do not reintroduce stateful stream engines in the MVP.

## Fixed names (do not rename without updating all docs)
- MCP tools: `search_articles`, `get_article`, `list_new_articles`, `submit_analysis`.
- Public article id is `url_hash` (sha256 of the normalized URL). `seq` (bigserial) drives the cursor, never expose it raw: the cursor is opaque base64.
- Tables: `articles`, `analyses`, `ingest_slot`. Slot format: `YYYYMMDDHHMMSS`.
- Dead-letter reasons: `missing_url`, `missing_title`, `bad_column_count`, `bad_field`.
- Agent score payload: `{relevant, score (0–1), reason}`; `submit_analysis` accepts any JSON object.

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

## Docs conventions
- Tag factual claims in specs/designs as **[verified]**, **[memory]** or **[assumption]**; only tag **[verified]** after checking this session.
- Keep `design.md` ≤ ~150 lines; detail goes in `design-detail.md`. Each design diagram has ≤ ~12 nodes and a "Check" box.
- ADRs live in `docs/adr/NNNN-<decision>.md` with a Status line; never treat a Proposed ADR as decided.

## Commands (run from the repo root; `make help` lists them)
- `make doctor` check tools; `make setup` install from lockfiles; `make check` everything (`check-python`, `check-web`, `docs-check`).
- `make test APP=<ingester|processor|sink|api|agent|web>` one app's tests; `make test-rules` proves each enforced rule fails when violated; `make test-infra` Docker tests (needs Docker, ports 5433 and 29092 free, no `.env` surprises: it backs up and restores your own).
- `make build [APP=<name>]` images (`newsdock-<app>:dev`, `newsdock-migrate:dev`); `cp .env.example .env` then `make up` / `make down`; `make topics`, `make migrate` are idempotent.
- Raw compose needs the env file: `docker compose --env-file .env -f infra/compose.yaml ps` (compose looks for `.env` next to the compose file otherwise).
- Python: `uv run ...` (never `pip`); one workspace, `uv sync --all-packages --locked`. Web: `pnpm --dir apps/web run <script>`; Node 24 comes from pnpm, not the system.
- Quality tools: ruff (lint, format, `TID251` bans `os.environ`/`os.getenv` outside `config.py`), mypy strict with the pydantic plugin, import-linter contracts in `pyproject.toml`, `infra/scripts/check_layout.py`, `infra/scripts/check_docs.py`.

## Environment notes
- Machine: macOS arm64. Docker Desktop 4.93, uv, pnpm and Ollama are installed; no Ollama model is pulled yet (needed for the manual AC-2 check and M1).
- A local Postgres already listens on 5432, so compose publishes Postgres on 5433 (`POSTGRES_PORT`).
- Spike findings and verified versions: `docs/specs/foundation/design-detail.md` §5, §6, §8, §11.

<!-- Maintainer note: keep this file under 200 lines; move topic-specific rules to .claude/rules/ with `paths` frontmatter once code exists. -->
