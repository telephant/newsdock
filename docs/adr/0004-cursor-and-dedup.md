# ADR-0004: Cursor = insert sequence; dedup at Postgres write

Status: **Accepted 2026-10-04**

## Context
AC-3/AC-6 need idempotent ingest and cross-slot dedup; AC-10 needs a cursor with "no new data → same cursor". D-6: pull with cursor.

## Options
1. Cursor = `seq` (insert order); dedup = Postgres unique `url_hash` only (stateless processor).
2. Cursor = `published_at` timestamp (late/old items break it).
3. Dedup also in processor state (needs Flink or a state store; rejected, see ADR-0001).

## Decision (proposed)
Option 1. Opaque base64 cursor so it can change later.

## Consequences
+ Late-arriving articles are never skipped. + One place holds dedup logic. − `seq` has gaps after conflicts (harmless).
