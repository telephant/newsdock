# newsdock — Roadmap

**Vision:** a shared "news dock" that ingests GDELT news once (clean, dedup, 7-day store) so any custom AI agent, such as a financial-relevance agent, can plug in. Also the owner's path from frontend engineer to AI production / full-stack engineer.

**Current milestone:** M1 (spec folder `mvp`), stage: **design approved**, next `/spec-plan mvp`.
Specs: [mvp spec](specs/mvp/spec.md) · Items: [backlog](specs/mvp/backlog.md) · Decisions: [ADRs](adr/) · Evidence: [research](../research.md)

| M | Goal | Skills it teaches / proves | Exit condition | Depends on | Status |
|---|---|---|---|---|---|
| M1 `mvp` | Walking skeleton: GDELT GKG → Kafka → Python processor → Postgres (7 d) → MCP + REST → demo agent (Ollama) → Next.js UI | Kafka basics, idempotent pipelines, real messy data, MCP server, LLM agent + eval, FastAPI, docker-compose, Next.js | AC-1…AC-15 pass; one `docker compose up` shows live articles; agent prints precision/recall | none | current |
| M2 | Make it a platform: push subscriptions, agent registry + auth, per-agent cursors | Event delivery (SSE/webhook/MCP notifications), API keys, multi-tenant design | TBD: decide at /spec-init | M1 | next |
| M3 | Richer data and AI stack: semantic search (pgvector), Events + Mentions, article body extraction | Embeddings, hybrid search, data modelling, legal/robustness of scraping | TBD: decide at /spec-init | M1 (M2 optional) | later |
| M4 | Production visibility: windowed stream analytics (trending themes/entities), observability | Windowing semantics (plain Python or Flink), OpenTelemetry, Prometheus/Grafana, Kafka lag | TBD: decide at /spec-init | M1 | later |
| M5 | Ship it: cloud deploy, CI/CD, public demo URL, agent eval harness | IaC (Terraform/K8s or managed), CI/CD, regression evals, model comparison | TBD: decide at /spec-init | M2, M4 **[assumption]** | later |
| M6 | Scale options: translation feed, microservice split, hosted LLM option | Multilingual NLP, service boundaries, provider-agnostic LLM layer | TBD: decide at /spec-init | M5 **[assumption]** | later |

Order follows backlog priorities (M2 = P1, M3–M5 = P2/P3 mixed); the dependency column is **[assumption]** until each milestone is specced.

**Not planned:** history backfill before the 7-day window; non-English-first processing in M1–M3; building a general-purpose agent framework.
