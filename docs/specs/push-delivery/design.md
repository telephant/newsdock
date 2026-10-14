# push-delivery — Design (Milestone 2, part 2)

Status: **approved** · 2026-10-14 · Spec: [spec.md](spec.md) · Detail (not required reading): [design-detail.md](design-detail.md)

**Reading order:** this file → `diagrams/index.html` (each diagram has a "Check" box) → ADR-0018 (Accepted), ADR-0019 in `../../adr/` → answer the checklist at the bottom.

## 1. Components (ids continue the numbering; unchanged components not listed)

| Id | Component | Change | Notes |
|---|---|---|---|
| C-15 | Subscriptions (`domain/subscriptions.py`, `adapters/subscriptions_repo.py`, `adapters/subscriptions_api.py`) | **new** | `SubscriptionFilter` (pydantic, `extra=forbid`), create/list/delete own over REST, per-agent cap |
| C-16 | SSE stream (`adapters/sse.py`) | **new** | `GET /api/subscriptions/{id}/stream`: start position, poll loop, event framing, keep-alive, revocation re-check (ADR-0018, ADR-0019) |
| C-17 | Stream cap + wake hub (`domain/streams.py`) | **new** | In-memory per-agent counter of open streams (acquire/release, 429 above the cap) and a pure `WakeHub`: streams wait on it, the listener wakes them |
| C-18 | NOTIFY listener (`adapters/listener.py`) + trigger | **new** | Migration 0005 trigger `pg_notify('articles_new', max seq)` once per insert statement; the API keeps one `LISTEN` connection (app lifespan), reconnects with backoff, wakes all streams on (re)connect (ADR-0018) |
| C-11 | Auth middleware | **changed** | Protects `/api/subscriptions*` too; also stores `key_id` in `scope["state"]` |
| C-14 | Admin routes | **changed** | `GET /api/admin/subscriptions` lists every agent's subscriptions |
| C-6 | API repo/service | **changed** | `list_new` takes optional `theme/domain/text`; theme supports a trailing `*` prefix (also applies to `search_articles`, backward compatible) |
| C-5 | PostgreSQL | **changed** | New table `subscriptions` and the `articles` insert trigger (migration 0005) |

Demo agent, sink, web: unchanged.

## 2. Key flows

- **F-11 Subscribe:** agent → C-11 (key) → C-15 `POST /api/subscriptions {filter}` → row stored. (Sequence 1)
- **F-12 Stream:** agent → C-11 → C-16: cap check (C-17) → start position → loop { query matching `seq > last` → emit events → wait for a wake-up (C-18) or the keep-alive tick → re-check key }. (Sequence 1)
- **F-15 New data:** sink commits articles → trigger `NOTIFY articles_new` → C-18 listener → `WakeHub` wakes all waiting streams → each re-queries by its own cursor. (Sequence 1)
- **F-13 Reconnect:** `Last-Event-ID: <cursor>` → same loop from that position; nothing before it is resent. (Sequence 1)
- **F-14 End of stream:** client disconnect, revoked key/disabled agent, or subscription deleted → loop exits, cap released. (State diagram 4)

## 3. Contracts

**`subscriptions`**: `id` uuid PK, `agent_id` FK→agents CASCADE, `filter` jsonb, `created_at`; index on `agent_id`. Deleting an agent removes its subscriptions.

| Route | Auth | Result |
|---|---|---|
| `POST /api/subscriptions` | agent key | 201 `{id, filter, created_at}`; 422 invalid; 409 over the per-agent cap |
| `GET /api/subscriptions` | agent key | own subscriptions |
| `DELETE /api/subscriptions/{id}` | agent key | 204; 404 if not own |
| `GET /api/subscriptions/{id}/stream` | agent key | `text/event-stream`; 404 not own; 429 over the cap; 400 bad `Last-Event-ID` |
| `GET /api/admin/subscriptions` | admin token | all subscriptions with agent name |

Event framing: `id: <cursor>` / `event: article` / `data: <ArticleSummary json>` and a blank line; keep-alive is the comment line `: ping`. The cursor is the existing opaque base64 (`seq` never exposed raw).

Config (ADR-0013, `api:` section): `sse_fallback_poll_seconds` (30), `sse_keepalive_seconds` (15), `sse_max_streams_per_agent` (5), `subscriptions_max_per_agent` (20), `subscription_text_max_length` (200).

## 4. Tricky parts

- **No gaps, duplicates allowed:** the loop sends in `seq` order and the id of an event is its own cursor, so `Last-Event-ID` resumes strictly after it; a reconnect before the client processed an event may repeat it (dedupe by `article_id`).
- **Start position (D-6):** `Last-Event-ID` > stored server cursor > first-run window. Streaming never writes `agent_cursors` (AC-10).
- **Filter semantics (D-7):** AND of given fields; theme with a trailing `*` is a prefix match over any of the article's themes, otherwise exact; empty filter matches all. One implementation in SQL (`list_new`), no second matcher in Python.
- **Wake-ups are hints, not data:** the notification payload is only the max `seq`; a stream never emits from it. Lost, early or duplicate notifications therefore cannot cause gaps or wrong rows, only an extra or a delayed query (bounded by the fallback poll).
- **Listener supervision:** reconnect with backoff; on every (re)connect wake all streams once; the fallback poll covers the rest of an outage.
- **Disconnects:** the generator runs under Starlette's streaming response; cancellation on disconnect must release the cap in `finally`. Spike first (plan T-01).
- **Revocation:** re-check each keep-alive tick; also re-check the subscription still exists.
- **Blocking DB calls** run in the threadpool; one slow stream cannot block the loop.

## 5. Failure modes (top)

| Failure | Result |
|---|---|
| Bad/revoked key | 401 before any event (AC-5); mid-stream: stream closes within one keep-alive |
| DB error in the loop | stream closes; the client reconnects with `Last-Event-ID` |
| Listener connection lost | streams fall back to the 30 s poll; listener reconnects and wakes everyone |
| Client too slow / gone | detected at disconnect; resources released |
| API restart | all streams drop; clients resume by id; subscriptions persist |
| Over the cap | 429, others unaffected |

## 6. Technology

Postgres `LISTEN/NOTIFY` via a dedicated psycopg connection (`psycopg` is already a dependency of the SQLAlchemy engine **[verified: packages/db]**). Otherwise existing stack: FastAPI `StreamingResponse` (`text/event-stream`), SQLAlchemy, Alembic. No new dependency **[assumption: spike confirms]**.

## 7. AC coverage

| AC | Component / flow |
|---|---|
| AC-1, AC-2 | C-15 / F-11 |
| AC-3, AC-4 | C-15, C-16 (ownership) |
| AC-5 | C-11, C-16 / F-12 |
| AC-6, AC-7 | C-16, C-6 (filtered `list_new`), C-18 / F-12, F-15 |
| AC-8 | C-16 / F-13 |
| AC-9, AC-10 | C-16 (start position, no cursor write) |
| AC-11 | C-16, C-11 (`key_id`) / F-14 |
| AC-12 | C-16 |
| AC-13 | C-17 |
| AC-14 | whole chain / F-12 (manual) |
| AC-15 | C-14 |

## Questions to answer before approving this design

- [x] Change detection is `LISTEN/NOTIFY` as a wake-up (ADR-0018, Accepted 2026-10-14; user choice).
- [x] Up to 15 s of continued delivery after key revocation is acceptable (ADR-0019, Accepted 2026-10-14).
- [x] A bad `Last-Event-ID` is a 400 `invalid_last_event_id` (2026-10-14).
- [x] `search_articles` shares the `ECON_*` prefix syntax (one implementation, 2026-10-14).
- [x] A hard 409 `too_many_subscriptions` at the per-agent cap (default 20, configurable) — **my default, not asked; change it if you prefer another behaviour.**
