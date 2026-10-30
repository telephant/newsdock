# ADR-0024: A separate embedder worker and a shared embedding package

Status: **Accepted 2026-10-28** (recommended default taken on the user's `/loop finish M3 by using /spec-*` instruction; revisit if you object)

## Context
Every canonical article title must get an embedding (spec `semantic-search`, D-3: ingestion never waits on it), and the API must embed query text the same way. CLAUDE.md requires an ADR for a new app, and apps may not import each other.

## Options
1. **Embed inside the sink** (same transaction or right after insert).
2. **New `apps/embedder` that polls Postgres for unembedded rows**, plus a new `packages/embedding` holding the Ollama client and text recipe, used by the worker and the API.
3. **Embed in a Kafka consumer** on `gkg.clean`.

## Decision
Option 2.
- The sink stays a fast, Kafka-to-Postgres writer; a slow or absent Ollama cannot slow or fail ingestion (AC-4).
- Polling the table (`embedding IS NULL`, served by the partial index `ix_articles_unembedded`, migration 0009) needs no new state: it backfills existing rows and is idempotent by construction; after a model change the worker clears the other model's vectors once at start and they flow through the same queue. (The first version filtered `embedding IS NULL OR embedding_model <> :model` over `ORDER BY seq DESC`, which made every pass and every idle poll walk past all embedded rows: 78 ms per idle poll at 67,000 rows, found at verify.) A Kafka consumer would need a second path for backfill and model changes.
- One package keeps the document/query prefixes, the endpoint and the vector validation in one place; the worker and the API cannot drift apart (AC-7, AC-11).
- `packages/embedding` is an I/O package like `packages/db`; `newsdock_core` stays free of I/O.

## Consequences
+ Ingestion is untouched. + Backfill, retry and model change are one code path. + The embedding recipe has one home.
− A ninth compose service and an app skeleton (Dockerfile, healthcheck, tests) to maintain.
− Polling adds a small constant query load and a delay between insert and embedding (seconds, not a requirement).
− The worker needs a route to Ollama on the host, like the demo agent.
