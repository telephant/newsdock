# mvp — Backlog (after Milestone 1)

Priority: P1 next, P2 soon, P3 later.

- **M2 Push subscriptions (P1):** agents register filters and receive matching articles via SSE/webhook/MCP notifications. Why: the "subscribe" idea in the vision.
- **M2 Agent registry + auth (P1):** API keys, agent profiles, per-agent cursors and quotas. Why: required before others use it.
- **M3 Semantic search (P2):** embeddings in pgvector, hybrid search MCP tool. Why: modern AI-stack skill.
- **M3 Events + Mentions streams (P2):** CAMEO events and mentions linked to GKG. Why: richer market-moving signal.
- **M3 Article body extraction (P2):** polite fetching and text extraction; legal review first.
- **M4 Windowed stream analytics (P2):** trending entities/themes, with Flink windows or plain Python. Why: real streaming semantics; Flink was dropped from the MVP (2026-10-04).
- **M4 Observability (P2):** OpenTelemetry, Prometheus/Grafana, Kafka lag dashboard.
- **M5 Cloud deploy (P2):** Terraform/K8s or managed services, public demo URL, CI/CD.
- **M5 Agent eval harness (P3):** versioned datasets, regression runs, model comparison.
- **M6 Translation feed + multilingual (P3).**
- **M6 Microservice split (P3):** split ingester/processor/API when scale or team justifies it.
- **M6 Hosted LLM option (P3):** Claude or other provider behind a provider-agnostic layer.

## Design TODOs (flow details not yet specified; resolve in /spec-plan or early tasks)
- [ ] Agent cursor persistence: where stored; save only after all submissions succeed; re-scoring is harmless (upsert).
- [ ] Expired-URL re-entry: with Postgres-only dedup an expired URL listed again re-enters; decide if acceptable.
- [ ] Compose startup order and health gating; Kafka topic creation (init job or auto-create).
- [ ] DB migrations approach (plain SQL files vs Alembic).
- [ ] UI pagination and refresh behaviour (keyset, polling interval).
- [ ] Processor: poison-message handling and consumer restart behaviour.
- [ ] Theme choice for column: use V2EnhancedThemes (col 9), strip offsets; empty themes are common (86/527 rows).
- [ ] Mixed-language/odd titles; quotation/entity noise in persons/orgs fields.
