# ui-login — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Webhook delivery (P2):** HMAC-signed POST to an agent-registered URL with retries and SSRF guard (from `push-delivery` backlog).
- **MCP notifications (P2):** server-initiated notifications on `/mcp`.
- **Demo agent consumes the stream (P2):** switch from polling to SSE.
- **Email verification and password reset (P2):** needs an email provider; not available locally.
- **Invites (P2):** owner-issued sign-up links, the safer alternative to open sign-up (D-3).
- **Audit log (P3):** who created/revoked what.
- **Key rotation overlap and scopes (P3).**
- **MFA / OAuth / SSO (P3).**
- **Editing subscriptions in the UI (P3):** agents own them today.
- **Richer filters (P3).**
- **Cloud deployment with TLS (M5):** `Secure` cookies on by default.
