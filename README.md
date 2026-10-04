# newsdock

News "dock" for AI agents: GDELT GKG → Kafka → Postgres → MCP/REST → agents and a web UI.

Status: design approved, no code yet. See `docs/specs/mvp/` and `research.md`.

## Layout
- `apps/` one folder per deployable service: `ingester`, `processor`, `sink`, `api`, `agent` (Python) and `web` (Next.js + TS)
- `packages/core` shared Python code
- `infra/` docker-compose, migrations, topic setup
- `docs/` specs, design, ADRs
