# forgot-password — Design (M2f)

Status: **approved** · 2026-10-29 · Spec: [spec.md](spec.md) · Detail (not required reading): [design-detail.md](design-detail.md)

**Reading order:** this file → `diagrams/index.html` (each diagram has a "Check" box) → ADR-0026, ADR-0027 in `../../adr/` (both Accepted 2026-10-29) → the checklist at the bottom.

## 1. Components (ids continue from C-40; unchanged components not listed)

| Id | Component | Change | Notes |
|---|---|---|---|
| C-41 | Reset rules (`domain/passwordreset.py`) | **new** | Pure: make a 6-digit code (`secrets`), keyed hash `HMAC-SHA256(secret, user_id:code)`, constant-time check, lifetime and attempt rules, the mail text. No I/O |
| C-42 | Reset store (`adapters/reset_repo.py`, table `password_resets`) | **new** | One open code per user (a new request replaces it); counts an attempt before checking; on success one transaction sets the password, deletes the code and ends the user's sessions |
| C-43 | Reset routes (`adapters/reset_api.py`) | **new** | `POST /api/auth/forgot-password`, `POST /api/auth/reset-password`, `GET /api/auth/options`; the foreground work is identical for known and unknown emails (ADR-0027) |
| C-44 | Mailer (`domain/mail.py` port, `adapters/smtp_mailer.py`) | **new** | `Mailer.send(to, subject, body)`; stdlib `smtplib` over STARTTLS or implicit TLS with a timeout; a fake in tests |
| C-45 | Reset limiters (`domain/resetlimit.py`) | **new** | Code requests: per client address, then per normalized email. Reset attempts: per client address. Bounded per-key windows built on C-30 (its total limit off) |
| C-46 | Migration `0010_password_resets` + `PasswordReset` model | **new** | The table, grants to `api_rw` |
| C-47 | Web screens (`features/auth`, routes `/forgot-password`, `/reset-password`) | **new** | Two forms, the login link, messages; both routes open in the page gate |
| C-48 | Settings, compose and docs | **changed** | `smtp_*`, `mail_from`, `auth_reset_*` in `api:`; secrets `NEWSDOCK_SMTP_PASSWORD` and `NEWSDOCK_RESET_CODE_SECRET` from the environment; README Brevo setup |
| C-17 | Recovery route (`make user-reset-password`) | unchanged | Operator path stays |
| C-10 | Accounts domain (`domain/accounts.py`: `normalize_email`, `check_password`, login-failure limiter) | **used** | The same email and password rules; a successful reset clears the user's login lockout, as the operator path does |
| C-11 | Users and sessions repo (`adapters/users_repo.py`) | **used** | `find_by_email`; the reset transaction in C-42 touches the same `users` and `sessions` tables |
| C-15 | Web page gate (`lib/gate.ts`) | **changed** | `/forgot-password` and `/reset-password` join the open paths |
| C-30 | `SignupLimiter` | **used** | C-45 is built from it, with its total limit switched off |

Demo agent, sink, embedder, MCP tools: unchanged.

## 2. Key flows

- **F-21 Request:** web → `POST /api/auth/forgot-password {email}` → JSON and Origin guards → feature on? (else 503) → email format (else 422) → limiter by address then by email (else 429) → **schedule the background job** → `202 {"ok": true}`. Known and unknown emails take exactly this path. (Sequence 1)
- **F-22 Issue and send (background):** look up the user; unknown → stop. Known → make a code, upsert the row (replaces the old code), delete expired rows, `Mailer.send`; on failure delete that row and log. (Sequence 1)
- **F-23 Reset:** web → `POST /api/auth/reset-password {email, code, password}` → guards → feature on? → email format and password policy (422, before touching the code) → attempt limiter by address (429) → code shape → user lookup → count an attempt and fetch the hash (open, unexpired, attempts below the cap) → constant-time compare → one transaction: set password, delete the code, delete sessions → clear the login lockout → `204`. Every refusal is `400 invalid_or_expired_code`. (Sequence 2)
- **F-24 Options:** the login page asks `GET /api/auth/options` and shows "Forgot password?" only when `password_reset_enabled` is true. (Sequence 1)
- **F-25 Code lifecycle:** open → (used | expired | locked after the attempt cap | replaced). (State diagram 4)

## 3. Contracts

| Route | Auth | Body | Result |
|---|---|---|---|
| `POST /api/auth/forgot-password` | none (JSON + Origin guards) | `{email}` | 202 `{"ok": true}`; 422 `invalid_email`; 429 `too_many_reset_requests` + `Retry-After`; 503 `password_reset_unavailable` |
| `POST /api/auth/reset-password` | none | `{email, code, password}` | 204; 400 `invalid_or_expired_code`; 422 `invalid_password` / `invalid_email`; 429 `too_many_reset_attempts` + `Retry-After`; 503 `password_reset_unavailable` |
| `GET /api/auth/options` | none | – | 200 `{"password_reset_enabled": bool}` |

**`password_resets`** (migration 0010): `user_id` uuid PK → `users` ON DELETE CASCADE, `code_hash` text, `expires_at` timestamptz, `attempts` int default 0, `created_at` timestamptz. One row per user, so "a newer request replaces the older" is an upsert.

**Mail:** subject `newsdock: your password reset code`; plain text with the code, the lifetime in minutes and "if you did not ask for this, ignore this message"; no link, no IP, no user name.

**Config (ADR-0013, `api:`)**: `smtp_host` ("" = feature off), `smtp_port` (587), `smtp_security` (`starttls` | `ssl` | `none`), `smtp_user`, `mail_from`, `smtp_timeout_seconds` (10), `auth_reset_code_minutes` (15), `auth_reset_max_attempts` (5), `auth_reset_max_per_email` (3), `auth_reset_max_per_address` (20), `auth_reset_max_tries_per_address` (20, reset attempts), `auth_reset_window_minutes` (60). **Secrets, environment only:** `NEWSDOCK_SMTP_PASSWORD`, `NEWSDOCK_RESET_CODE_SECRET` (at least 32 characters). The feature is on only when `smtp_host`, `mail_from` and the code secret are all set. The numbers are the spec's provisional defaults.

## 4. Tricky parts

- **No enumeration, also by timing (D-4, D-8):** the handler does the same work for known and unknown emails (validate, limit, schedule); the lookup, the code, the database write and the SMTP send all happen in the background job. The 202 body and status never vary.
- **Codes are small, so the hash needs a secret (ADR-0026):** a plain hash of a 6-digit code is crackable in microseconds; with a keyed hash, a database leak alone does not yield usable codes. Attempts per code are capped and counted in the database before the comparison, so concurrent guesses cannot exceed the cap.
- **Single use under concurrency:** success deletes the row inside the same transaction that sets the password and ends the sessions; a second concurrent success finds no row.
- **Order of checks in F-23:** the password policy comes before the attempt is counted, so a weak password does not burn the code (AC-10); a malformed code or unknown email gives the same 400 as a wrong code and does a dummy comparison so timing is similar.
- **Mail abuse and guessing (AC-11, AC-12, AC-17):** for requests the address limit comes first (cheap, protects the relay), the email limit second; reset attempts have their own per-address limit before any code is looked at; all are in memory (one worker). Open codes are also bounded per user by the upsert.
- **Failure of the mail:** the user already got 202; the background job deletes the unsent code and logs the failure without the code, the address or the password.
- **Secrets in logs:** log only the user id and outcome. The SMTP library's debug output stays off.
- **TLS rule:** `smtp_security: none` is accepted only for loopback hosts (tests, a local relay); any other host must use STARTTLS or SSL, or the API refuses to start.

## 5. Failure modes (top)

| Failure | Result |
|---|---|
| SMTP refused, timeout, bad credentials | generic 202; the code is deleted; error logged (AC-14) |
| Database down in the background job | generic 202; nothing sent; logged. Reset itself answers 503 `unavailable` |
| SMTP not configured | both routes 503 `password_reset_unavailable`; the login page shows no link |
| Code guessed wrongly 5 times | the code is locked until it expires or is replaced (AC-6) |
| API restart | open codes survive (database); the in-memory request limits reset |
| Mailbox of the user compromised | account takeover; the operator path remains for owners (spec risk 2) |
| Provider quota (Brevo: 300/day) reached | sends fail like any SMTP failure; users get no mail and can retry later |

## 6. Technology

Python standard library only: `smtplib`, `email.message`, `secrets`, `hmac`, `hashlib`, `ssl` **[verified: Python docs for `smtplib`: `starttls` then `ehlo` then `login`, `SMTP_SSL`, `timeout`, `send_message`; `SMTPException` is an `OSError`]**. FastAPI `BackgroundTasks`, SQLAlchemy 2 and Alembic as today. No new dependency; the SMTP adapter is tested against a small standard-library SMTP server in the test suite. Brevo's connection settings (host `smtp-relay.brevo.com`, 587/465, login and SMTP key) are **[secondary sources]**; its help page could not be fetched.

## 7. AC coverage

| AC | Component / flow |
|---|---|
| AC-1 | C-43, C-44 / F-21, F-22 (live server, slow mailer) |
| AC-2 | C-41, C-42, C-44 / F-22 |
| AC-3 | C-43, C-42 / F-21, F-22 |
| AC-4 | C-43, C-41, C-42 / F-23 |
| AC-5 | C-42 / F-23, F-25 |
| AC-6 | C-42, C-41 / F-23, F-25 |
| AC-7 | C-41, C-42 / F-23, F-25 |
| AC-8 | C-42 / F-22, F-25 |
| AC-9 | C-42 / F-23 |
| AC-10 | C-43 / F-23 |
| AC-11, AC-12 | C-45 / F-21 |
| AC-17 | C-45, C-43 / F-23 |
| AC-13 | C-48, C-43 / F-21, F-23 |
| AC-14 | C-43, C-44, C-42 / F-22 |
| AC-15 | C-43, C-47 / F-24 |
| AC-16 | C-47 / F-21, F-23 |

## Questions to answer before approving this design

- [x] ADR-0026: reset codes are hashed with a keyed HMAC, which makes `NEWSDOCK_RESET_CODE_SECRET` a second operator secret next to the SMTP password (user, 2026-10-29).
- [x] ADR-0027: all work that differs between known and unknown emails (lookup, database write, send) runs after the response, so a database error there can only be logged, never returned (user, 2026-10-29).
- [x] The login page learns whether to show the link from a public `GET /api/auth/options`, not from a second flag in the web config (user, 2026-10-29).
- [x] A per-address limit on `reset-password` attempts is added: spec D-9, AC-17 (user, 2026-10-29).
- [x] A successful reset also clears the user's login lockout, as the operator path does (my default, not asked; change it if you prefer the lockout to stay).
