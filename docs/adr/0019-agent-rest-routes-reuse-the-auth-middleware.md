# ADR-0019: Agent REST routes reuse the auth middleware; open streams re-check the key

Status: **Accepted 2026-10-14** (user accepted at /spec-design push-delivery)

## Context
ADR-0016 guards `/mcp*` with one pure-ASGI middleware. Subscriptions and streams are REST routes that must be agent-authenticated, while public `GET /api/articles*` and `/api/health` stay open (agent-platform D-7) and `/api/admin/*` uses the admin token. A stream outlives the request that authenticated it, so a key revoked mid-stream must still end it (AC-11).

## Options
**Where to authenticate:** (a) **extend the middleware's protected prefixes with `/api/subscriptions`**; (b) a FastAPI dependency on those routes (a second implementation of the same check).
**Revocation of open streams:** (a) **the stream loop re-checks `key usable` every keep-alive interval and closes when it is not**; (b) track connections per key and close them from the admin routes (cross-task signalling); (c) accept until reconnect.

## Decision (proposed)
Both (a). The middleware also stores `key_id` next to the agent in `scope["state"]` so the stream can re-check cheaply (`SqlAgentsRepo.key_usable(key_id)`). Revocation latency is at most one keep-alive interval (default 15 s).

## Consequences
One enforcement point stays one enforcement point. A revoked key can keep receiving events for up to 15 s (documented). The middleware rate-limits stream *opens*, not events; the concurrent-stream cap covers the long-lived resource.
