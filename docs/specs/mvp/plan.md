# mvp — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation (2026-10-05)

| # | Check | Method | Result |
|---|---|---|---|
| 1 | AC → test coverage | grep AC column of tests.md | **pass**: AC-1…AC-15 each ≥ 1 TC (35 TCs, no orphans) |
| 2 | AC → design / task coverage | grep design.md §7; `Implements:` in tasks/ | **pass**: 15/15 in both |
| 3 | Cross-doc names | grep topics, tools, tables, dlq reasons, statuses across spec/design/tests/tasks | **pass** |
| 4 | Proposed ADRs treated as decided | grep `Proposed` in docs/adr + mvp docs | **pass**: none |
| 5 | Untagged claims / invented numbers / glossary | review numbers in tests and tasks | **pass**: targets stay in Measurements, not ACs |
| 6 | Scope leaks from backlog.md | grep backlog items in tasks | **pass**: backlog only under "Out of scope" |
| 7 | Open questions / unchecked items | grep `- [ ]` in mvp docs | **pass**: only owner prerequisites (labels) and future measurement notes |

**Carried from the design review (retired 2026-10-05, verdict approve):**
- R-10 (minor, accepted): AC-3/AC-7 need test hooks — `process_slot(slot, force=True)`, injectable retention clock. In T-04/T-06, TC-6/TC-13.
- R-11 (minor, accepted): Ollama model unchosen — chosen and timed in the T-01 spike.
- R-12 (minor, accepted): expired-URL re-entry accepted; cross-slot duplicate rate measured (Measurements table).

**Verdict: GO.** `gates.plan: approved`.

## Spike first

**T-01** de-risks the two riskiest unverified claims at once: the `mcp` SDK v2 streamable-HTTP API has never been read (ADR-0003's fallback is 1.x), and no Ollama model has been chosen or timed (R-11; R-2's throughput math assumes the agent keeps up with ~500 rows/15 min after the ~24 % theme pre-filter). Half a day; outputs are recorded in design.md §6 and a short `spike.md`.

## Tasks (walking skeleton order)

| Phase | Task | Title | ACs | Effort |
|---|---|---|---|---|
| P0 spike | T-01 | MCP v2 API + Ollama model choice + scoring speed | (enables 8, 14) | 0.5 d |
| P1 pipeline | T-02 | GKG parsing + contracts in `newsdock_core` (+ fixtures) | 4, 5 | 1 d |
| | T-03 | ORM models + Alembic `0002` in `newsdock_db` | 5, 7 | 0.5 d |
| | T-04 | Ingester (C-1): poll, slot state, publish raw | 1, 2, 3 | 1 d |
| | T-05 | Processor (C-3): raw → clean / dlq | 4, 5 | 0.5 d |
| | T-06 | Sink + retention (C-4): upsert, poison fallback, delete | 3, 6, 7 | 1 d |
| P2 serve | T-07 | API (C-6): MCP tools + REST over one service layer | 8, 9, 10, 11 | 1.5 d |
| | T-08 | Demo agent (C-7): loop, pre-filter, score, cursor file | 10, 13, 14 | 1 d |
| | T-09 | Eval command + labelling helper | 14 | 0.5 d |
| P3 visible | T-10 | Web UI (C-8): feed, filters, detail, generated types | 12 | 1.5 d |
| | T-11 | Compose integration: networks, healthchecks, README, measurements | 13, 15 | 1 d |

**Progress:** T-01 ✅ 2026-10-05 — findings in [spike.md](spike.md): mcp v2 confirmed, model `llama3.2:3b`, pre-filter default `ECON_` only (both user decisions 2026-10-05). T-02 ✅ 2026-10-05 — `newsdock_core` gkg/urls/contracts + real fixtures; TC-7, TC-8, TC-10, TC-11 green. T-03 ✅ 2026-10-05 — ORM models + Alembic 0002 + roles; TC-34, TC-14 green (`make test-infra` now covers all docker-marked tests). T-04 ✅ 2026-10-05 — ingester (domain cycle + http/kafka/sql adapters, force hook, heartbeat); TC-1…TC-5 + TC-2 green. T-05 ✅ 2026-10-05 — processor (route + Kafka loop, manual commits); TC-9 green. T-06 ✅ 2026-10-05 — sink (batch upsert RETURNING, poison fallback, retention with injected clock, dedup counter); TC-31, TC-13, TC-6, TC-12 green (TC-6 lives in infra/scripts/tests: cross-app). T-07 ✅ 2026-10-05 — API: one service layer under MCP (`/mcp`, ToolError for not_found/payload_too_large) + REST (`/api/*`), cursor b64(seq), 1 h first-run window, ILIKE escaping, clamped limits, latest-score map for the UI, `/api/health`; TC-15…TC-24 green. T-08 ✅ 2026-10-05 — agent: loop with ECON_ pre-filter, clamped score parsing, cursor-after-batch, file cursor store, MCP+Ollama adapters; TC-29, TC-32, TC-35 green. T-09 ✅ 2026-10-05 — eval command (`python -m newsdock_agent.eval --labels …`, production prompt/schema, threshold 0.5, prints P/R/F1/confusion/skipped) + `export_labels` REST helper; TC-28 green (fake scorer; the owner's ≥50-label real run happens at /spec-verify). T-10 ✅ 2026-10-05 — web UI: feed (filters, score badge, keyset load-more, 60 s polling), detail view, OpenAPI-generated types (`pnpm run generate:api`); REST gained the designed `before` keyset + typed responses; TC-26 green. T-11 ✅ 2026-10-05 — compose: `data`/`agent` networks, healthchecks on all 8 (native/HTTP/heartbeat), agent on `agent` network only with `agent_state` volume, MCP transport allows Host `api:*` (421 fix), README (architecture, GDELT attribution, honesty notes); TC-27, TC-33 green on the live stack; all 8 healthy with a real GDELT slot ingested (1317 rows) and 51 live agent analyses; measurements recorded in tests.md.

**Milestone markers:** after T-06 → live data lands in Postgres (AC-1…AC-7). After T-09 → agent round-trip + eval (AC-8…AC-11, AC-14). After T-11 → human-visible, end-to-end ready for `/spec-verify` (AC-12, AC-13, AC-15). Total ≈ 10 working days.

## Definition of Done (every task)

1. Tests named in the task written **first** and turned green (`make test APP=<name>`, docker-marked ones via `make test-infra`).
2. `make check` green; CI green if pushed.
3. Docs updated in the same change when a fact moved (design/detail/CLAUDE.md fixed names); ADR updated if a decision changed (needs user approval).
4. No secrets committed; `.env.example` extended instead.
5. `status.yaml` AC statuses updated by `/spec-implement`.

Out of scope for this plan: everything in [backlog.md](backlog.md) (push, auth, embeddings, Events/Mentions, scraping, cloud, observability).
