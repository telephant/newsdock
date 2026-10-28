# signup-rate-limit — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Trusted-proxy setting (P2):** honour `X-Forwarded-For` only from configured proxy addresses, so the limiter sees real clients behind a reverse proxy (D-6).
- **Persistent / multi-worker limiter (P3):** counters in Postgres or Redis so restarts and more than one worker do not reset or multiply the limits.
- **Invites (P2, from the ui-login backlog):** owner-issued sign-up links, the safer alternative to open sign-up.
- **CAPTCHA or proof-of-work (P3):** only if a flood gets past the limiter.
- **Email verification (P2, from the ui-login backlog):** needs an email provider.
- **Delete an agent (P2):** the quota is a hard stop until agents can be deleted; today only disable exists.
- **Per-user quotas for keys and subscriptions (P3).**
- **Show remaining quota in the UI (P3).**
