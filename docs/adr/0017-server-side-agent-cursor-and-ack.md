# ADR-0017: Per-agent cursor stored by the API, advanced by an explicit `ack_cursor` tool

Status: **Accepted 2026-10-14** (user accepted at /spec-design agent-platform; MCP tool, not REST or implicit ack)

## Context
The cursor today is an opaque base64 of `seq` kept by the client (ADR-0004, agent file on a volume). M2 wants it per agent, server-side, surviving agent restarts and redeploys (spec AC-8, AC-9). It must stay at-least-once: an agent that crashes mid-batch must see the batch again.

## Options
(a) Advance the stored cursor when `list_new_articles` returns (at-most-once: a crash loses a batch).
(b) **Advance only when the agent calls a new MCP tool `ack_cursor(cursor)` after finishing the batch.**
(c) Keep client-side cursors only.

## Decision (proposed)
(b). Table `agent_cursors(agent_id PK, seq bigint, updated_at)`. `list_new_articles` without `cursor` starts from the stored position (or the first-run window when none); an explicit `cursor` argument still wins and is not stored. `ack_cursor` moves forward only (`GREATEST`), is idempotent, and is rejected for the anonymous agent. The client-side cursor stays opaque (`seq` is never exposed raw). New fixed MCP tool name: `ack_cursor` (CLAUDE.md "Fixed names" and the mvp design must be updated when accepted).

## Consequences
Two calls per batch instead of one; a crash between submit and ack re-scores a batch (analyses upsert, harmless). Moving a cursor backwards (replay) is not supported in this spec. `push-delivery` reuses the same table for SSE resume.
