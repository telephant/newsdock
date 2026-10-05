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
- [x] `design-detail.md` §8 updated for M0 decisions (R-13, 2026-10-05).
- [x] SQLAlchemy layer: ORM 2.0 declarative in `newsdock_db` (R-14, user decision 2026-10-05).
- [x] Agent cursor persistence: decided 2026-10-04 (R-2): file on named volume `agent_state`, saved after the whole batch succeeds; re-scoring is harmless (upsert).
- [x] Expired-URL re-entry: accepted for the MVP (2026-10-04, R-12). Still to do: measure the cross-slot duplicate rate over several consecutive slots and revisit if material.
- [x] Compose startup order and topic creation: resolved by M0 (`make up` waits on kafka/postgres health, `topics` init job) plus healthchecks on all 8 services (design-detail §4, R-4).
- [x] DB migrations approach: Alembic in `infra/migrations/` (ADR-0008).
- [x] UI pagination and refresh: keyset `before=<published_at,url_hash>` + polling (design-detail §3, task T-10).
- [x] Processor poison handling and restart: per-row catch → dlq `bad_field`, manual commits, stateless restart (design-detail §2/§5, task T-05).
- [x] Theme column: V2EnhancedThemes (col 9), strip offsets, fall back to col 8; empty is normal (design-detail §2, task T-02).
- [x] Mixed-language/odd titles and entity noise: accepted as-is for M1 (stored verbatim); watch during live runs, revisit if the agent or UI suffers.

- **Duplicate-rate soak (P2, R-12):** measure the cross-slot duplicate rate over ≥ 4 consecutive live slots (SQL: conflicts vs inserts, counter already logged by the sink); revisit dedup if material. 0/2 slots on 2026-10-05.
- **Future `published_at` clamp (P3):** GDELT's publisher-supplied precise timestamp is sometimes hours in the future and pins articles to the feed top; option: clamp to `ingested_at` when `published_at > now`. Owner saw and accepted it on 2026-10-05.
- **Faster `make test-infra` (P3):** parallelize docker test modules with pytest-xdist (`--dist loadfile`) by parameterizing host ports (`KAFKA_PORT`, `API_PORT`, `WEB_PORT` next to the existing `POSTGRES_PORT`) so each compose project binds unique ports; warm suite ~5 min → ~2 min. Found 2026-10-05 while fixing a hung M0 image test.

## Plan inputs from the design review (2026-10-04)
- [x] Test hooks carried into the plan: `process_slot(force=True)` in T-04 (TC-6), injectable clock in T-06 (TC-13). (R-10)
- [x] First spike is task T-01: Ollama model choice + seconds/score + `mcp` v2 API read. (R-11, R-2)
- [x] README honesty notes (slot gaps on downtime, Kafka for learning) carried into task T-11. (R-8)
