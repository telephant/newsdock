# mvp — Design (Milestone 1)

Status: **approved** · 2026-10-04 · Spec: [spec.md](spec.md) · Detail (not required reading): [design-detail.md](design-detail.md)

**Reading order:** this file → `diagrams/index.html` (open in a browser; each diagram has a "Check" box) → ADRs in `../../adr/` → answer the checklist at the bottom.

## 1. Components

| Id | Component | Job | Notes |
|---|---|---|---|
| C-1 | Ingester (Python, asyncio) | Poll `lastupdate.txt`, download + md5-check GKG zip, publish one raw message per row, track slot state | Never polls faster than 15 min; 404/empty = retry later |
| C-2 | Kafka (KRaft, single broker) | Topics `gkg.raw`, `gkg.clean`, `gkg.dlq` | 1 partition each in MVP (ordering, simplicity) |
| C-3 | Processor (Python, confluent-kafka) | Consume `gkg.raw`, parse 27 columns, validate, route to `gkg.clean` or `gkg.dlq`; stateless | Plain consumer group, manual offset commit (ADR-0001) |
| C-4 | Sink + retention (Python) | Consume `gkg.clean`, upsert into Postgres, commit offset after write; hourly retention delete | Idempotent writes (ADR-0002) |
| C-5 | PostgreSQL 16 + pgvector | `articles`, `analyses`, `ingest_slot` | pgvector extension installed, unused |
| C-6 | API service (FastAPI) | One process: MCP server (streamable HTTP, `/mcp`) + REST (`/api/*`) over one service layer | Only component besides C-4 and C-1 holding DB credentials (ADR-0003) |
| C-7 | Demo agent (Python) | MCP client; list new → score with Ollama → `submit_analysis`; plus `eval` command | No DB credentials, not on the DB network (AC-13) |
| C-8 | Web UI (Next.js + TS) | Feed with filters, detail view, agent score | Talks to REST only |
| C-9 | Ollama (on host, not in compose) | Local LLM for C-7 | Reached via `host.docker.internal` |

## 2. Key flows

- **F-1 Ingest cycle:** C-1 → C-2 `gkg.raw` → C-3 → `gkg.clean` / `gkg.dlq` → C-4 → C-5. (Sequence diagram 2)
- **F-2 Agent run:** C-7 → C-6 `list_new_articles(cursor)` → Ollama → C-6 `submit_analysis`. (Sequence diagram 3)
- **F-3 Human browse:** C-8 → C-6 REST `GET /api/articles` → C-5. (Component diagram 1)
- **F-4 Retention:** C-4 scheduler deletes rows with `ingested_at` older than 7 days (analyses cascade). (State diagram 5)

## 3. Contracts

**Kafka topics** (JSON values, UTF-8)

| Topic | Key | Value |
|---|---|---|
| `gkg.raw` | `<slot>:<row_no>` | `{slot, row_no, line}` (`line` = untouched TSV row) |
| `gkg.clean` | `url_hash` | `{url_hash, gkg_record_id, slot, url, title, domain, published_at, themes[], persons[], orgs[], tone{tone,positive,negative,polarity,word_count}}` |
| `gkg.dlq` | `<slot>:<row_no>` | `{reason, slot, row_no, line (≤2 KB), at}`; reasons: `missing_url`, `missing_title`, `bad_column_count`, `bad_field` |

**MCP tools** (C-6) — same names everywhere

| Tool | Input | Output |
|---|---|---|
| `search_articles` | `time_from?, time_to?, theme?, domain?, text?, limit (default 20, max 100)` | `articles[]` (summary form) |
| `get_article` | `article_id` (= `url_hash`) | article + `analyses[]` |
| `list_new_articles` | `cursor?, limit (default 50, max 200)` | `articles[], next_cursor` |
| `submit_analysis` | `article_id, agent_name, payload (JSON object)` | `{ok}` |

**REST** (C-6, for UI): `GET /api/articles?theme&domain&text&from&to&limit&before`, `GET /api/articles/{article_id}`, `GET /api/health`. Detail in design-detail.

## 4. Tricky parts

- **Dedup + idempotency (AC-3, AC-6):** one layer, in Postgres: `PRIMARY KEY (url_hash)` + `ON CONFLICT DO NOTHING`. The processor is stateless, so `gkg.clean` may carry duplicates; the sink absorbs them. Re-ingesting a slot never changes the count.
- **Slot state:** `ingest_slot` row per slot: `pending → published`. A slot is `published` only after every row is flushed to Kafka. Pending slots are retried each cycle up to 4 attempts, so a 404 never causes a gap (AC-2).
- **Cursor (AC-10):** opaque base64 of the highest `seq` seen (`seq` = `bigserial`, assigned by the single writer C-4). Same cursor with no new data → empty list, same cursor back.
- **Ordering:** none guaranteed across slots; the UI sorts by `published_at`, cursors use `seq` (insert order).
- **Retention clock:** `ingested_at` (not `published_at`), so old re-reported items are still kept 7 days after we first see them.

## 5. Top failure modes

| Failure | Effect | Handling |
|---|---|---|
| GKG file 404/empty | slot missing | stay `pending`, retry next cycle (AC-2) |
| Processor crash/restart | messages redelivered | stateless, outputs idempotent downstream |
| C-4 crash after write, before commit | message redelivered | upsert is a no-op |
| Postgres down | sink stalls, Kafka buffers | no commit; resumes on recovery |
| Ollama down/slow | agent run fails | agent logs, leaves cursor unchanged, retries |
| Malformed row | would poison the job | caught → `gkg.dlq` (AC-4) |

## 6. Technology

Python 3.12 + `confluent-kafka` **[memory]**; Apache Kafka 4.x KRaft **[assumption]**; PostgreSQL 16 + pgvector **[memory]**; FastAPI + official `mcp` SDK 2.x streamable HTTP **[verified: v2.3.0 current, 2026-10-02; v2 API not read, see ADR-0003]**; Ollama with a ~3–4B instruct model and JSON-schema structured output **[memory]**; Next.js + TypeScript; docker-compose; pytest. Flink dropped (2026-10-04, ADR-0001). Diagrams: Mermaid 11.15 (cdnjs).

## 7. AC coverage

| AC | Covered by | Where |
|---|---|---|
| AC-1 | C-1 → C-2 | F-1, `gkg.raw` |
| AC-2 | C-1 | `ingest_slot` pending/retry |
| AC-3 | C-1, C-4, C-5 | Postgres dedup |
| AC-4 | C-3 | `gkg.dlq` |
| AC-5 | C-3, C-4 | `gkg.clean` contract |
| AC-6 | C-4, C-5 | Postgres dedup |
| AC-7 | C-4, C-5 | F-4 |
| AC-8 | C-6 | MCP tools |
| AC-9 | C-6, C-5 | `search_articles` |
| AC-10 | C-6 | cursor |
| AC-11 | C-6, C-5 | `submit_analysis` / `get_article` |
| AC-12 | C-8, C-6 | F-3 |
| AC-13 | C-7, compose networks | agent has no DB route |
| AC-14 | C-7 | `eval` command |
| AC-15 | C-1…C-9 | compose + healthchecks |

## 8. Questions to answer before approving this design

- [x] ADR-0001: plain Python processor instead of Flink (user decision 2026-10-04)?
- [x] ADR-0002: separate Python sink consumer writes Postgres?
- [x] ADR-0003: one API process serving MCP and REST, on `mcp` SDK 2.x?
- [x] ADR-0004: cursor is Postgres insert sequence; dedup at the Postgres write only?
- [x] Retention measured from `ingested_at` rather than `published_at`?
- [x] `get_article` / REST use `url_hash` as the public article id?
- [x] Demo agent score payload shape `{relevant, score 0–1, reason}` fixed by convention, with `submit_analysis` accepting any JSON object?
- [x] Docker and Ollama are not installed on this machine yet: accept installing them as the first implementation task?
