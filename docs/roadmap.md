# newsdock — Roadmap

**Vision:** a shared "news dock" that ingests GDELT news once (clean, dedup, 7-day store) so any custom AI agent, such as a financial-relevance agent, can plug in. Also the owner's path from frontend engineer to AI production / full-stack engineer.

**Current milestone:** M2 (platform), in progress: `agent-platform` and `push-delivery` are done (both verified 2026-10-14, pass with follow-ups); `ui-login` (multi-user accounts + roles, login-gated UI, management screens, live feed) is done (verified 2026-10-27, pass with follow-ups: [verify](specs/ui-login/verify.md)). **M2 is complete**, and so is M2c `ui-design` (shadcn/ui restyle of every screen, verified 2026-10-27, pass with follow-ups: [verify](specs/ui-design/verify.md)). M2d `agent-ownership` (agents belong to their creator, [spec](specs/agent-ownership/spec.md)) is done (verified 2026-10-28, pass with follow-ups: [verify](specs/agent-ownership/verify.md)). M2e `signup-rate-limit` (sign-up limiter and a per-user agent quota, [spec](specs/signup-rate-limit/spec.md)) is done (verified 2026-10-28, pass with follow-ups: [verify](specs/signup-rate-limit/verify.md)). Webhook delivery, MCP notifications and the demo agent on the SSE stream are deferred (decided 2026-10-28: agents pull through MCP, and SSE already covers push; they stay in the [push-delivery backlog](specs/push-delivery/backlog.md)). M3 part 1 `semantic-search` (pgvector title embeddings filled by the new `embedder` app, MCP tool `semantic_search` in `vector` and `hybrid` mode, recall eval; [spec](specs/semantic-search/spec.md), ADR-0024/0025) is done (verified 2026-10-29, pass with follow-ups: [verify](specs/semantic-search/verify.md)); M3 continues with body extraction and Events + Mentions. The `make test-infra` scenes stay unrun for now (open in two verifies, P2). Done before: M0 `foundation` (2026-10-05), M1 `mvp` (verified 2026-10-05, all 15 ACs, F1 0.83, live end-to-end), M2a `dedup-syndication` (verified 2026-10-09) and M2b `externalize-config` (verified 2026-10-07), all pass with follow-ups.
Specs: [foundation](specs/foundation/spec.md) · [mvp](specs/mvp/spec.md) · Items: [mvp backlog](specs/mvp/backlog.md), [foundation backlog](specs/foundation/backlog.md) · Decisions: [ADRs](adr/) · Evidence: [research](research.md)

| M | Goal | Skills it teaches / proves | Exit condition | Depends on | Status |
|---|---|---|---|---|---|
| M0 `foundation` | Project setup: service boundaries recorded, toolchain installed, repo and infra skeleton, CI, docs | Monorepo tooling (uv workspace, pnpm), Docker/compose, CI path filters, ADR and docs hygiene | 17 ACs verified; CI green on `main`; a clean clone reaches green `make check` and healthy `make up` from the README | none | done |
| M1 `mvp` | Walking skeleton: GDELT GKG → Kafka → Python processor → Postgres (7 d) → MCP + REST → demo agent (Ollama) → Next.js UI; also OpenAPI-generated UI types and worker healthchecks (foundation backlog, P1) | Kafka basics, idempotent pipelines, real messy data, MCP server, LLM agent + eval, FastAPI, Next.js | AC-1…AC-15 pass; one-command start (`make up`; spec AC-15 still says `docker compose up`) shows live articles; agent prints precision/recall | M0 | done |
| M2b `externalize-config` | Every tunable out of the code: one hierarchical YAML (`common` + service sections), env > file > defaults, secrets env-only, config-derived healthchecks, web runtime config | Layered configuration (12-factor), typed settings, Docker config mounts, runtime config in a Next.js image | AC-1…AC-14 pass; `make check` green; `make up` healthy with the file mounted | M2a | done (verified 2026-10-07, pass with follow-ups) |
| M2 | Make it a platform, split in three specs (2026-10-14): `agent-platform` (registry, API keys, per-agent cursors, rate limits; spec'd, init approved) → `push-delivery` (filters, SSE, webhook, MCP notifications) → `ui-login` (multi-user accounts + roles) | Event delivery, API keys, multi-tenant design, auth | see [agent-platform spec](specs/agent-platform/spec.md) | M1 | done (2026-10-27): `agent-platform` verified 2026-10-14, pass with follow-ups; `push-delivery` verified 2026-10-14, pass with follow-ups; `ui-login` verified 2026-10-27, pass with follow-ups |
| M2c `ui-design` | Visual redesign of the Next.js UI in the spirit of the LINE website (requested 2026-10-27): friendly, clean, rounded, one green-leaning accent, generous whitespace, light and dark. Covers feed, article, login/sign-up, management screens and `/live`. Inspiration only, no LINE logo, fonts or assets. Takes the P3 "Unstyled UI" item from the [ui-login backlog](specs/ui-login/backlog.md) | Design tokens and a small component system, responsive layout, accessibility (contrast, focus, reduced motion), styling in Next.js without a UI-kit lock-in **[assumption]** | AC-1…AC-14 of the [spec](specs/ui-design/spec.md) pass: every screen on shared tokens and components, no behaviour or API change, existing web tests green, 375 and 1280 px screenshots in light and dark reviewed | M2 (`ui-login`) | done (verified 2026-10-27, pass with follow-ups: [verify](specs/ui-design/verify.md); [ADR-0022](adr/0022-shadcn-ui-on-tailwind-v4.md)) |
| M2d `agent-ownership` | Agents belong to the user who created them (requested 2026-10-28): `agents.owner_id`, a required `AgentScope` in the repos, every role manages its own agents and subscriptions, the `owner` role sees all, agents with no creator are managed by the owner role and the admin token only | Authorization by resource ownership (row-level filtering, 404 for foreign ids), safe additive migration | AC-1…AC-11 of the [spec](specs/agent-ownership/spec.md) pass; existing role tests updated; `make check` green | M2 (`ui-login`) | done (verified 2026-10-28, pass with follow-ups: [verify](specs/agent-ownership/verify.md); [ADR-0023](adr/0023-agent-ownership-by-scope-filter.md)) |
| M2e `signup-rate-limit` | Limit account sign-ups and cap agents per user (requested 2026-10-28 after agent-ownership made every account worth more): in-memory per-address and global sign-up windows (429, `Retry-After`), `agents_max_per_user` (409), web messages | Rate limiting with two keys, a bounded in-memory table with an injectable clock, a resource quota enforced where the resource is created | AC-1…AC-15 of the [spec](specs/signup-rate-limit/spec.md) pass; `make check` green | M2d | done (verified 2026-10-28, pass with follow-ups: [verify](specs/signup-rate-limit/verify.md)) |
| M3a `semantic-search` | Search by meaning: a separate `embedder` app embeds canonical article titles with `nomic-embed-text` (Ollama, host) into pgvector (HNSW cosine); the MCP tool `semantic_search` runs a vector leg and, in `hybrid` mode, a full-text leg fused by reciprocal rank; recall eval (`make eval-search`). Titles only: GKG has no body | Embeddings, ANN indexes and filtered search, hybrid ranking, a decoupled worker, evaluating retrieval | AC-1…AC-15 of the [spec](specs/semantic-search/spec.md) pass; `make check` green | M1 | done (verified 2026-10-29, pass with follow-ups: [verify](specs/semantic-search/verify.md)); [ADR-0024](adr/0024-embedder-worker-and-embedding-package.md), [ADR-0025](adr/0025-embeddings-as-columns-hnsw-cosine-and-fts-keyword-leg.md) |
| M3 (rest) | Richer data: Events + Mentions streams, article body extraction (then embeddings of more than titles) | Data modelling, legal/robustness of scraping | TBD: decide at /spec-init | M3a | later |
| M4 | Production visibility: windowed stream analytics (trending themes/entities), observability | Windowing semantics (plain Python or Flink), OpenTelemetry, Prometheus/Grafana, Kafka lag | TBD: decide at /spec-init | M1 | later |
| M5 | Ship it: cloud deploy (CD; CI exists since M0), public demo URL, agent eval harness | IaC (Terraform/K8s or managed), CD, regression evals, model comparison | TBD: decide at /spec-init | M2, M4 **[assumption]** | later |
| M6 | Scale options: translation feed, hosted LLM option | Multilingual NLP, provider-agnostic LLM layer | TBD: decide at /spec-init | M5 **[assumption]** | later |

Order follows backlog priorities (M2 = P1, M3–M5 = P2/P3 mixed); reviewed and kept 2026-10-05. The dependency column is **[assumption]** until each milestone is specced.

## M1 system map (design approved 2026-10-05)

Source of truth: [design.md](specs/mvp/design.md) (ids C-n, flows F-n) and [diagrams](specs/mvp/diagrams/index.html); this map is a snapshot of M1 and does not show the M2 additions (accounts and sessions, agent registry and keys, subscriptions with SSE, the NOTIFY listener, the live feed) — update it when the design changes.

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

**Not planned:** history backfill before the 7-day window; non-English-first processing in M1–M3; building a general-purpose agent framework; copying LINE's branding or assets (M2c takes style inspiration only).
