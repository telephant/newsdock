# newsdock

News "dock" for AI agents: ingests the GDELT GKG feed every 15 min, cleans it with a Python Kafka processor, keeps 7 days in Postgres, and serves it to agents through an MCP server and REST. Local docker-compose only. Milestone 1 (MVP) is a walking skeleton.

## Status
- Stage: design approved; next is `/spec-plan mvp`. No application code exists yet.
- Roadmap: `docs/roadmap.md` (current milestone: M1).
- Source of truth, in this order: `docs/specs/mvp/spec.md` (ACs) → `docs/specs/mvp/design.md` → `docs/adr/` → `docs/specs/mvp/design-detail.md`.
- Real GDELT evidence and a sample row: `research.md`. Check it before assuming anything about the data.
- Open items: `docs/specs/mvp/backlog.md` ("Design TODOs"). Pending change: `published_at` should prefer `<PAGE_PRECISEPUBTIMESTAMP>` over column 2 (not yet applied to design docs).

## Repo layout (monorepo, Python + TypeScript in one git repo)
- `apps/<service>/` one deployable per folder: `ingester`, `processor`, `sink`, `api`, `agent` (Python) and `web` (Next.js + TS). Each app owns its dependency file and Dockerfile.
- `packages/core/` shared Python code (GKG parsing, URL normalisation, models). Apps may import `packages/*`, never another app.
- `infra/` docker-compose, SQL migrations, Kafka topic setup. `docs/` specs and ADRs.
- The only link between Python and TS is the REST/OpenAPI contract; generate the UI's types from it instead of hand-writing them.
- Python: one `uv` workspace at the root (planned); web: its own `package.json` in `apps/web`. CI jobs run only for the apps whose files changed.

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

## GDELT rules (verified in `research.md`)
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

## Environment notes
- Docker and Ollama are not installed yet; installing them is the first implementation task (T-00).
- Git repo initialised on `main`, no commits yet. `uv` and `pnpm` are not installed; system Python is 3.9 (need 3.12+). Add these to T-00.
- Build, test and run commands do not exist yet. Add them here when the first tasks create them, instead of guessing.

<!-- Maintainer note: keep this file under 200 lines; move topic-specific rules to .claude/rules/ with `paths` frontmatter once code exists. -->
