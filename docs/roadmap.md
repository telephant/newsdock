# newsdock — Roadmap

**Vision:** a shared "news dock" that ingests GDELT news once (clean, dedup, 7-day store) so any custom AI agent, such as a financial-relevance agent, can plug in. Also the owner's path from frontend engineer to AI production / full-stack engineer.

**Current milestone:** M1 `mvp` is **done** (verified pass-with-follow-ups 2026-10-05, [verify](specs/mvp/verify.md): all 15 ACs pass, F1 0.83, live end-to-end). Current: **M2b `externalize-config`** (spec'd 2026-10-06, verified 2026-10-07 pass with follow-ups: one YAML config file with env overrides) after **M2a `dedup-syndication`** (committed 2026-10-07, verification pending); then M2 (push subscriptions + agent registry/auth, backlog P1). M0 `foundation` done (2026-10-05).
Specs: [foundation](specs/foundation/spec.md) · [mvp](specs/mvp/spec.md) · Items: [mvp backlog](specs/mvp/backlog.md), [foundation backlog](specs/foundation/backlog.md) · Decisions: [ADRs](adr/) · Evidence: [research](research.md)

| M | Goal | Skills it teaches / proves | Exit condition | Depends on | Status |
|---|---|---|---|---|---|
| M0 `foundation` | Project setup: service boundaries recorded, toolchain installed, repo and infra skeleton, CI, docs | Monorepo tooling (uv workspace, pnpm), Docker/compose, CI path filters, ADR and docs hygiene | 17 ACs verified; CI green on `main`; a clean clone reaches green `make check` and healthy `make up` from the README | none | done |
| M1 `mvp` | Walking skeleton: GDELT GKG → Kafka → Python processor → Postgres (7 d) → MCP + REST → demo agent (Ollama) → Next.js UI; also OpenAPI-generated UI types and worker healthchecks (foundation backlog, P1) | Kafka basics, idempotent pipelines, real messy data, MCP server, LLM agent + eval, FastAPI, Next.js | AC-1…AC-15 pass; one-command start (`make up`; spec AC-15 still says `docker compose up`) shows live articles; agent prints precision/recall | M0 | done |
| M2b `externalize-config` | Every tunable out of the code: one hierarchical YAML (`common` + service sections), env > file > defaults, secrets env-only, config-derived healthchecks, web runtime config | Layered configuration (12-factor), typed settings, Docker config mounts, runtime config in a Next.js image | AC-1…AC-14 pass; `make check` green; `make up` healthy with the file mounted | M2a | done (verified 2026-10-07, pass with follow-ups) |
| M2 | Make it a platform: push subscriptions, agent registry + auth, per-agent cursors | Event delivery (SSE/webhook/MCP notifications), API keys, multi-tenant design | TBD: decide at /spec-init | M1 | later |
| M3 | Richer data and AI stack: semantic search (pgvector), Events + Mentions, article body extraction | Embeddings, hybrid search, data modelling, legal/robustness of scraping | TBD: decide at /spec-init | M1 (M2 optional) | later |
| M4 | Production visibility: windowed stream analytics (trending themes/entities), observability | Windowing semantics (plain Python or Flink), OpenTelemetry, Prometheus/Grafana, Kafka lag | TBD: decide at /spec-init | M1 | later |
| M5 | Ship it: cloud deploy (CD; CI exists since M0), public demo URL, agent eval harness | IaC (Terraform/K8s or managed), CD, regression evals, model comparison | TBD: decide at /spec-init | M2, M4 **[assumption]** | later |
| M6 | Scale options: translation feed, hosted LLM option | Multilingual NLP, provider-agnostic LLM layer | TBD: decide at /spec-init | M5 **[assumption]** | later |

Order follows backlog priorities (M2 = P1, M3–M5 = P2/P3 mixed); reviewed and kept 2026-10-05. The dependency column is **[assumption]** until each milestone is specced.

## M1 system map (design approved 2026-10-05)

Source of truth: [design.md](specs/mvp/design.md) (ids C-n, flows F-n) and [diagrams](specs/mvp/diagrams/index.html); this map is a snapshot — update it when the design changes.

```
  GDELT GKG feed                         ┌─ docker network: data ─────────────────────────────┐
  lastupdate.txt + *.gkg.csv.zip         │                                                    │
  (15-min slots; newest can 404)         │            C-2 Kafka 4.x KRaft (1 broker)          │
        │                                │            topics: gkg.raw | gkg.clean | gkg.dlq   │
        │ poll ≥ 900 s, md5-check        │              ▲        │               ▲            │
        ▼                                │       raw    │        │ clean         │ dlq        │
  ┌─────────────┐  1 msg per TSV row     │        ┌─────┘        ▼               │(bad rows,  │
  │ C-1 Ingester├────────────────────────┼────────┘   ┌──────────────┐           │ bad_field) │
  │  (asyncio)  │  slot state:           │            │ C-3 Processor│───────────┤            │
  └─────────────┘  pending→published     │            │  (stateless) │ parse 27  │            │
        │          └→ failed after 4     │            └──────┬───────┘ cols,     │            │
        │ ingest_slot r/w                │                   │ clean   validate  │            │
        ▼                                │                   ▼                   │            │
  ┌──────────────────────────┐  upsert   │            ┌──────────────┐───────────┘            │
  │ C-5 PostgreSQL 16        │◄──────────┼────────────│ C-4 Sink +   │ ON CONFLICT DO NOTHING │
  │  + pgvector (unused)     │  seq,     │            │  retention   │ batch 200, row-retry   │
  │  articles / analyses /   │  dedup    │            └──────────────┘ 7-day ingested_at      │
  │  ingest_slot             │           │                                                    │
  │  [SQLAlchemy 2 ORM +     │           │            ┌──────────────┐                        │
  │   Alembic, newsdock_db]  │◄──────────┼────────────│ C-6 API      │                        │
  └──────────────────────────┘  read +   │            │  (FastAPI)   │                        │
                                analyses │            │ /mcp + /api/*│                        │
                                         └────────────┴──────┬───────┴────────────────────────┘
                                         ┌─ docker network: agent ──┼─────────────────────────┐
                                         │         ▲                ▲                         │
                              MCP tools: │         │ MCP (HTTP)     │ REST                    │
                              search_articles      │                │                         │
                              get_article │  ┌─────┴──────┐   ┌─────┴──────┐                  │
                              list_new_articles│ C-7 Demo │   │ C-8 Web UI │                  │
                              submit_analysis  │   agent  │   │ (Next.js)  │                  │
                                         │  └─────┬──────┘   └────────────┘                  │
                                         │        │ cursor → /data/cursor.json               │
                                         └────────┼──────────(volume: agent_state)───────────┘
                                                  │ score (theme-prefiltered, ECON_/WB_)
                                                  ▼
                                         C-9 Ollama (host, ~3–4B instruct,
                                         via host.docker.internal)

  Flows: F-1 ingest  C-1→raw→C-3→clean/dlq→C-4→C-5      F-3 browse  C-8→C-6 REST→C-5
         F-2 agent   C-7→C-6 list_new(cursor)→Ollama→submit_analysis
         F-4 retention  C-4 hourly DELETE ingested_at < now()−7d (analyses cascade)

  Guarantees: dedup = PK(url_hash)+ON CONFLICT (one layer) · cursor = b64(seq) single-writer
              at-least-once everywhere, idempotent writes · C-7 has no DB/Kafka route (AC-13)
  Health:     all 8 compose services (native / HTTP / heartbeat-file) — AC-15
```

## Small stages
**M0 delivered** ([plan](specs/foundation/plan.md), T-00…T-14): service-boundary ADR, toolchain, uv/pnpm skeleton, compose Kafka + Postgres, Alembic baseline, path-filtered CI, docs. The service split (5 Python apps + web, ADR-0005) is already done, so the old "M6 microservice split" is retired.
**M1** (from spec §4; `/spec-plan` sets the real tasks **[assumption]**): ingest → Kafka raw → processor → sink + Postgres → API (MCP + REST) → agent + eval → UI → end-to-end on compose.
**M2–M6:** stages are the backlog items tagged with the milestone; see the mvp backlog.
**Follow-ups outside milestones** ([foundation backlog](specs/foundation/backlog.md)): P1 items land in M1; pin or test the CI runner image before GitHub moves `ubuntu-latest` to Ubuntu 26 on 2026-10-19; P2/P3 hygiene (pre-commit, dependency bot, secret scan, caching, image scanning).

**Not planned:** history backfill before the 7-day window; non-English-first processing in M1–M3; building a general-purpose agent framework.
