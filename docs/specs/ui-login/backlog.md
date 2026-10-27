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
- **Rate-limit sign-up (P2):** open sign-up has no limiter, so a flood creates viewer rows (spec risk 1); `auth_signup_open: false` is the only brake today.
- **Other browsers (P3):** the cross-port cookie and `EventSource` behaviour was verified in Chrome only; repeat M-1 and M-3 in Safari and Firefox.
- **Stream keeps the session alive (P3):** an open live page refreshes `last_seen_at` through the keep-alive check, so an open tab never idles out (it still ends at the 7-day absolute limit); decide whether the stream should leave `last_seen_at` alone.
- **Login throttle is per process (P3):** failure counters live in memory (one API worker); move them to Postgres before running more than one worker.
- ~~**Unstyled UI (P3):** all new screens are plain HTML; a design pass belongs with the UI work in a later milestone.~~ Done by M2c `ui-design` (implemented 2026-10-27, shadcn/ui on Tailwind v4; spec `docs/specs/ui-design/`).
- **Hand-run full `make up` (P3):** `/spec-verify` ran every `make test-infra` scene (db, kafka, sink, api, pipeline, e2e, stack, images: green) but not a manual full stack with real GDELT ingestion and the demo agent.
- **Hard-coded alembic head in `test_stack.py` (P3, found at verify):** TC-26 asserted `0005`, so migration `0006` broke it; read the head from the migration scripts so the next migration cannot.
- **Cloud deployment with TLS (M5):** `Secure` cookies on by default.
