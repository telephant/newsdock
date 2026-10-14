# push-delivery — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **ui-login (P1, third M2 spec):** multi-user accounts + roles for the Next.js UI; replaces the admin token as the human path to agents, keys and subscriptions (decided 2026-10-14 in `agent-platform`).
- **Webhook delivery (P2):** server POSTs matches to an agent-registered URL with an HMAC signature, retries with backoff and a dead-letter state; needs an SSRF guard (block private/loopback ranges, DNS-rebinding aware). Decided order in `agent-platform` D-3: SSE → webhook → MCP notifications.
- **MCP notifications (P2):** server-initiated notifications on `/mcp` for subscribed agents; depends on client support (uneven) **[assumption]**.
- **Demo agent consumes the stream (P2):** switch the demo agent from polling `list_new_articles` to the SSE stream (keeps polling as fallback).
- **Richer filters (P3):** persons/orgs, minimum `source_count`, score thresholds from other agents' analyses.
- **Per-agent subscription and stream quotas beyond the concurrent-stream cap (P3).**
- **Live feed in the web UI (P3):** needs UI auth first (`ui-login`).
