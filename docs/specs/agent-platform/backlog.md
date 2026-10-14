# agent-platform — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later. M2 is split into three sequential specs (D-1).

- **push-delivery (P1, next spec):** saved filters per agent, then push in this order: SSE stream (resumes from the agent's server-side cursor) → webhook (HMAC, retries, SSRF guard) → MCP notifications. Why: the "subscribe" idea in the vision; builds on the per-agent cursor from this spec.
- **ui-login (P1, third spec):** multi-user accounts + roles for the Next.js UI (owner/admin/viewer), password hashing, sessions, agent and key management screens. Replaces the admin token as the human path to the registry. Decided 2026-10-14: multi-user with roles (not single-owner, not OAuth).
- **Key rotation with overlap window (P2):** two valid keys per agent during rotation.
- **Per-key scopes (P2):** read-only vs. read+submit_analysis keys.
- **Quota by analysis volume / storage (P3):** this spec only rate-limits requests.
- **Audit log of admin actions (P3).**
- **Agent: one MCP session per batch (P2):** the demo agent opens a session per call (~4 HTTP requests per scored article, found in the T-08 live run); reuse one session per run to cut requests ~4x and relax the rate limit.
- **Allow `.claude/` in the layout check or ignore Claude Code's loop lock (P3):** `check_layout.py` DR-1 fails while `.claude/scheduled_tasks.lock` exists.
