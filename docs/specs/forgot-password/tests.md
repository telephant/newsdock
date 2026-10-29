# forgot-password — Tests

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Plan: [plan.md](plan.md)

## Test data

- **No real email is ever sent by an automated test.** The mailer is a port: tests use `FakeMailer` (records messages, can raise `MailError`, can block on an event), defined in the one test module that needs it. The SMTP adapter is exercised against a tiny standard-library SMTP server (`StubSmtpServer`, a threaded socket server speaking EHLO, MAIL, RCPT, DATA, QUIT) defined in `apps/api/tests/unit/test_smtp_mailer.py`, and its TLS logic against a fake `smtplib` object.
- **Clock:** the routes take an injectable `now` (`create_app(..., reset_clock=)`), so expiry (AC-7) never sleeps.
- **Database:** every Docker test takes the `side_db` fixture (own Postgres on a free port); hand-made users via the real signup route or SQL. No fixtures from GDELT.
- **Secrets in tests** are made-up strings (`test-reset-secret-…` of 32+ characters, `smtp-password-for-tests`); the log test asserts they never appear in captured logs.
- **Live server (AC-1):** a uvicorn thread like the other live tests, because Starlette's `TestClient` finishes background tasks before it returns (T-01 confirms).
- **Web:** vitest with a stubbed `fetch`, as `LoginForm.test.tsx`.

## Tests

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | integration (live server, Docker) | Given an account and a mailer whose `send` blocks on an event, When forgot-password is called, Then the 202 arrives while the send is still blocked, and the message is delivered once the event is set |
| TC-2 | AC-2 | integration (Docker) | Given an account and a fake mailer, When a code is requested, Then exactly one message went to that address with a 6-digit code, the lifetime in minutes and no `http`; the `password_resets` row holds a 64-hex-character hash, not the code, and it equals `hash_code(secret, user_id, code)` |
| TC-3 | AC-2 | unit | Given the stub SMTP server (plain, loopback), When `SmtpMailer.send` sends a message, Then the server received From, To, Subject and the body text intact |
| TC-4 | AC-3 | integration (Docker) | Given no account for `nobody@example.com`, When forgot-password is called with it and with a known email, Then status and JSON body are equal, the fake mailer got nothing for the unknown one and no row exists |
| TC-5 | AC-4 | integration (Docker) | Given a code for ada, When reset-password is called with email, code and a valid password, Then 204; login with the new password returns 200 and with the old one 401 |
| TC-6 | AC-5 | integration (Docker) | Given a code already used, When reset-password is called again with it (and a different valid password), Then 400 `invalid_or_expired_code` and the password from the first use still works |
| TC-7 | AC-6 | integration (Docker) | Given a code and the cap N (5), When N wrong codes then the correct one are sent, Then all N+1 answers are 400 `invalid_or_expired_code` with the same body as for an unknown email, and the row has `attempts = N` |
| TC-8 | AC-7 | integration (Docker) | Given a code and the injected clock moved past its lifetime, When the correct code is sent, Then 400 `invalid_or_expired_code` |
| TC-9 | AC-8 | integration (Docker) | Given two requests for ada, When the first code and then the second are used, Then the first is refused and the second sets the password; only one row exists for ada |
| TC-10 | AC-9 | integration (Docker) | Given ada logged in twice and bob once, When ada's reset succeeds, Then both of ada's sessions answer 401 and bob's still answers 200 |
| TC-11 | AC-10 | integration (Docker) | Given a code, When reset-password is called with a 3-character password, Then 422 `invalid_password`, `attempts` is still 0, and the same code then works with a valid password |
| TC-12 | AC-11 | integration (Docker) | Given a limit of M (3) per email, When M+1 requests are made for one email, known and (in a second run) unknown, Then the last is 429 `too_many_reset_requests` with `Retry-After`, the same for both kinds, and the fake mailer has M messages for the known one |
| TC-13 | AC-12 | integration (Docker) | Given a limit of K (20) per address (set to 3 in the test), When K+1 requests come from one address for different emails, Then the last is 429 with `Retry-After` and no extra mail; a request from another address is accepted |
| TC-14 | AC-13 | integration (Docker) | Given no SMTP host (and, in variants, no sender or no secret), When forgot-password and reset-password are called, Then both are 503 `password_reset_unavailable`, `password_resets` is empty, nothing was sent, and `GET /api/auth/options` says false |
| TC-15 | AC-14 | integration (Docker) | Given a mailer that raises `MailError` and captured logs, When a code is requested for a known email, Then 202 with the generic body, the row is gone, a failure is logged, and no log record contains the code, the SMTP password or the reset secret |
| TC-16 | AC-15 | unit (web) | Given `GET /api/auth/options` answers true, When the login form renders, Then "Forgot password?" is shown and links to `/forgot-password`; given false, an error or no answer, the link is absent |
| TC-17 | AC-16 | unit (web) | Given a stubbed API, When a user submits an email then a code and a new password, Then they see the generic confirmation, then "Password changed" with a link to `/login`; a 400 shows the uniform code error with a link to request a new one; 422, 429 and 503 show their messages |
| TC-18 | AC-17 | integration (Docker) | Given a limit of J (3 in the test) reset attempts per address, When J+1 well-formed calls are made from one address, Then the last is 429 `too_many_reset_attempts` with `Retry-After` even if its code is right, and the same call from another address is not refused |
| TC-19 | AC-2 | unit | `new_code` is 6 digits (property over many draws), `hash_code` depends on secret, user id and code, `matches` is true only for the right triple, and a different user id never matches |
| TC-20 | AC-11, AC-12, AC-17 | unit | The limiters count unknown keys, refuse after the limit with a positive `Retry-After`, record nothing on refusal, are bounded in size, treat 0 as off, and normalize emails (case, spaces) |
| TC-21 | AC-13 | unit | `password_reset_enabled` is true only with host, sender and a secret of at least 32 characters; a shorter secret, `smtp_security=none` with a non-loopback host, or a secret/password key in the YAML stops startup with a clear error; env beats file beats default |
| TC-22 | AC-14 | unit | With a fake `smtplib`: `starttls` mode calls starttls, then ehlo, then login, then send; `ssl` mode uses `SMTP_SSL` and logs in; `none` is refused for a non-loopback host; any `OSError` (connection, timeout, auth, refused recipients) becomes `MailError` whose text has no address, code or password |
| TC-23 | AC-5, AC-6 | integration (Docker) | The reset store: `claim_attempt` increments once per call and returns nothing at the cap, after expiry or without a row; two threads calling `complete` for one code give exactly one success; `complete` rolls back if the code row is gone; deleting the user removes the row |
| TC-24 | AC-8 | integration (Docker) | Migration 0010: the table, primary key on `user_id`, cascade, `api_rw` grants; the ORM model matches the migration (autogenerate no-op); an upsert keeps one row per user |

## Coverage

Every AC has at least one test: AC-1 TC-1 · AC-2 TC-2, TC-3, TC-19 · AC-3 TC-4 · AC-4 TC-5 · AC-5 TC-6, TC-23 · AC-6 TC-7, TC-23 · AC-7 TC-8 · AC-8 TC-9, TC-24 · AC-9 TC-10 · AC-10 TC-11 · AC-11 TC-12, TC-20 · AC-12 TC-13, TC-20 · AC-13 TC-14, TC-21 · AC-14 TC-15, TC-22 · AC-15 TC-16 · AC-16 TC-17 · AC-17 TC-18, TC-20.

## Optional manual check (needs your provider account; not part of `make check`)

Run once after T-08, with a real Brevo (or other SMTP) account; nothing here is automated.

- [ ] `.env` has `NEWSDOCK_SMTP_PASSWORD` and `NEWSDOCK_RESET_CODE_SECRET`; `newsdock.yaml` (or env) has `smtp_host`, `smtp_port`, `smtp_security`, `smtp_user`, `mail_from`.
- [ ] `GET /api/auth/options` returns `{"password_reset_enabled": true}` after restarting the API.
- [ ] Request a code for your own account: the mail arrives within a minute (check spam) with a 6-digit code and no link.
- [ ] Enter the code and a new password in the web app: "Password changed", log in with the new password.
- [ ] The same code a second time is refused.
- [ ] Request for an address with no account: the web shows the same confirmation and no mail arrives.

## Measurements (provisional targets; not pass/fail)

| What | How |
|---|---|
| Foreground latency of forgot-password, known vs unknown email | 200 requests each against the live test server with a fake mailer; compare medians and p95 (they should not differ beyond noise) |
| Time from request to mail in the inbox | the manual check above, with a clock |
| Mails a day against the provider's quota | the provider's dashboard after normal use (Brevo free plan: 300/day) |
