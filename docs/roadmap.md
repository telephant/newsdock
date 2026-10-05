# newsdock — Roadmap

**Vision:** a shared "news dock" that ingests GDELT news once (clean, dedup, 7-day store) so any custom AI agent, such as a financial-relevance agent, can plug in. Also the owner's path from frontend engineer to AI production / full-stack engineer.

**Current milestone:** M0 (spec folder `foundation`), stage: **plan approved**, next `/spec-implement foundation`. M1 (`mvp`) is design-approved and waits for M0 before `/spec-plan mvp`.
Specs: [mvp spec](specs/mvp/spec.md) · Items: [backlog](specs/mvp/backlog.md) · Decisions: [ADRs](adr/) · Evidence: [research](../research.md)

| M | Goal | Skills it teaches / proves | Exit condition | Depends on | Status |
|---|---|---|---|---|---|
| M0 `foundation` | Project setup: service boundaries recorded, toolchain installed, repo and infra skeleton, CI skeleton, docs. Replaces the T-00 setup task | Monorepo tooling (uv workspace, pnpm), Docker/compose, CI path filters, ADR and docs hygiene | Fresh clone: one check command (lint, types, tests) is green on empty skeletons; compose brings up Kafka + Postgres healthy; every app has README, Dockerfile, dependency file and a passing smoke test; `CLAUDE.md` lists the real commands | none | current |
| M1 `mvp` | Walking skeleton: GDELT GKG → Kafka → Python processor → Postgres (7 d) → MCP + REST → demo agent (Ollama) → Next.js UI | Kafka basics, idempotent pipelines, real messy data, MCP server, LLM agent + eval, FastAPI, docker-compose, Next.js | AC-1…AC-15 pass; one `docker compose up` shows live articles; agent prints precision/recall | M0 | next (design approved) |
| M2 | Make it a platform: push subscriptions, agent registry + auth, per-agent cursors | Event delivery (SSE/webhook/MCP notifications), API keys, multi-tenant design | TBD: decide at /spec-init | M1 | later |
| M3 | Richer data and AI stack: semantic search (pgvector), Events + Mentions, article body extraction | Embeddings, hybrid search, data modelling, legal/robustness of scraping | TBD: decide at /spec-init | M1 (M2 optional) | later |
| M4 | Production visibility: windowed stream analytics (trending themes/entities), observability | Windowing semantics (plain Python or Flink), OpenTelemetry, Prometheus/Grafana, Kafka lag | TBD: decide at /spec-init | M1 | later |
| M5 | Ship it: cloud deploy, CI/CD, public demo URL, agent eval harness | IaC (Terraform/K8s or managed), CI/CD, regression evals, model comparison | TBD: decide at /spec-init | M2, M4 **[assumption]** | later |
| M6 | Scale options: translation feed, microservice split, hosted LLM option | Multilingual NLP, service boundaries, provider-agnostic LLM layer | TBD: decide at /spec-init | M5 **[assumption]** | later |

Order follows backlog priorities (M2 = P1, M3–M5 = P2/P3 mixed); the dependency column is **[assumption]** until each milestone is specced.

## Small stages
**M0** (proposed; `/spec-init foundation` confirms them):
1. Service boundaries ADR: one deployable per responsibility. Pipeline side = `ingester`, `processor`, `sink`; serving side = `api` (MCP + REST); isolated `agent`; `web`. Merging into 2 backend services was considered and not chosen (2026-10-04).
2. Toolchain installed and versions pinned: Docker, Ollama (+ one small model), Python 3.12+, uv, pnpm, Node.
3. Repo skeleton: uv workspace (`apps/*`, `packages/core`), `apps/web` Next.js scaffold, per-app dependency file, Dockerfile, README and smoke test, one check command.
4. Infra skeleton: compose with Kafka + Postgres healthy, topic setup, migrations approach (plain SQL vs Alembic), `.env.example`.
5. CI skeleton: path-filtered jobs run the check command.
6. Docs: README run/test commands, `CLAUDE.md` commands, per-app README (purpose, entrypoint, owned dependencies), docs index.

**M1** (from spec §4; `/spec-plan` sets the real tasks **[assumption]**): ingest → Kafka raw → processor → sink + Postgres → API (MCP + REST) → agent + eval → UI → end-to-end on compose.
**M2–M6:** stages are the backlog items tagged with the milestone; see the backlog.

**Not planned:** history backfill before the 7-day window; non-English-first processing in M1–M3; building a general-purpose agent framework.
