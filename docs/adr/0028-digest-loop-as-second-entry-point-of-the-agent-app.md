# ADR-0028: The what-happen digest is a second entry point of `apps/agent`

Status: Accepted 2026-10-30 (the user chose this in spec decisions D-1 and D-2)

## Context

The `what-happen` digest agent (M2g, [spec](../specs/what-happen/spec.md)) reads articles through MCP, asks a local model for short summaries and writes markdown files. It is a test harness for the server. The directory rules say an app owns its dependency file and Dockerfile, apps never import each other, and a new app needs an ADR. `apps/agent` already holds an MCP client, an Ollama client, settings that forbid database and Kafka keys, and a heartbeat healthcheck.

## Options

1. **New app `apps/whathappen`.** Clean separation; copies the small MCP and Ollama adapters (apps cannot import each other); a new Dockerfile, lockfile entry, CI path and image.
2. **A second entry point (`python -m newsdock_agent.digest`) in `apps/agent`, run as a second compose service from the same image.** Reuses the adapters and the isolation rules; no new app.
3. **Share the existing scoring loop and add the digest to it.** Rejected: one cursor would serve two jobs and one failure would stall both.

## Decision

Option 2. The digest has its own module, its own settings (`digest_*`), its own compose service and its own registered agent key, so it has its own server-side cursor. The scoring loop is not touched.

## Consequences

- No new Dockerfile, CI job or lockfile entry; the isolation test for the agent network covers the new service.
- The two loops share one `Settings` class; fields stay independent. If the digest grows (UI, storage), moving it to its own app is mechanical because `domain/` is pure and the adapters are small.
- The image carries the digest code even when only the scoring agent runs; accepted for a local harness.
- Two services use two keys, so `make agent-create NAME=<digest agent>` is a one-time step and `.env` gains `NEWSDOCK_DIGEST_API_KEY`.
