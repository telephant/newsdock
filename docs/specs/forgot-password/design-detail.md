# forgot-password — Design detail

Reference only; not required reading for approval. Overview: [design.md](design.md).

## 1. Schema (migration `0010_password_resets`, after `0009`)

```sql
CREATE TABLE password_resets (
  user_id    uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  code_hash  text        NOT NULL,            -- hex HMAC-SHA256, never the code
  expires_at timestamptz NOT NULL,
  attempts   integer     NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL
);
CREATE INDEX ix_password_resets_expires_at ON password_resets (expires_at);  -- cleanup
GRANT SELECT, INSERT, UPDATE, DELETE ON password_resets TO api_rw;
```

- One row per user: a new request is `INSERT … ON CONFLICT (user_id) DO UPDATE` (new hash, new expiry, `attempts = 0`), which is how a newer code replaces the older (AC-8). Deleting a user removes the row (cascade).
- Forward-only (DR-11); the `PasswordReset` ORM model carries the same index so the autogenerate test stays a no-op.

## 2. Domain (`domain/passwordreset.py`, pure)

- `new_code() -> str`: `f"{secrets.randbelow(10**6):06d}"`.
- `hash_code(secret: str, user_id: str, code: str) -> str`: `hmac.new(secret.encode(), f"{user_id}:{code}".encode(), sha256).hexdigest()`. Binding the user id means a leaked row cannot be replayed for another user.
- `matches(stored: str, secret, user_id, code) -> bool`: `hmac.compare_digest`.
- `expires_at(now, minutes)`; `DUMMY_USER_ID` for the timing-equalizing comparison on unknown emails.
- `reset_mail(code, minutes) -> (subject, body)`: the text in design.md §3.
- `ResetSettings` (frozen dataclass): `code_minutes`, `max_attempts`, `secret`; `enabled` is decided in `config.py`.

## 3. Store (`adapters/reset_repo.py`, role `api_rw`; every statement parameterized)

```
issue(user_id, code_hash, expires_at, now)       # upsert as above
discard(user_id, code_hash)                      # DELETE … WHERE user_id=:u AND code_hash=:h  (unsent code)
delete_expired(now)                              # DELETE … WHERE expires_at < :now
claim_attempt(user_id, now, max_attempts) -> str | None
    UPDATE password_resets SET attempts = attempts + 1
     WHERE user_id = :u AND expires_at > :now AND attempts < :max
 RETURNING code_hash
complete(user_id, code_hash, new_password_hash) -> bool      # ONE transaction
    DELETE FROM password_resets WHERE user_id=:u AND code_hash=:h      -- rowcount must be 1
    UPDATE users SET password_hash=:p WHERE id=:u
    DELETE FROM sessions WHERE user_id=:u
```

- `claim_attempt` counts the attempt *before* the comparison, in one statement, so parallel guesses cannot exceed the cap; the row stays (attempts = max) until it expires or is replaced, which is the "locked" state.
- `complete` rolls back entirely if the delete finds no row (a concurrent success), so a code works once.
- The clock is a parameter everywhere (`now`), so AC-7 uses an injected clock, not sleeps.

## 4. Routes (`adapters/reset_api.py`)

**`POST /api/auth/forgot-password`** (foreground, identical for every email):

```
1. feature disabled            -> 503 password_reset_unavailable
2. normalize_email fails       -> 422 invalid_email
3. limiter.attempt(address, email) refused -> 429 too_many_reset_requests, Retry-After
4. background.add_task(issue_and_send, email)
5. return 202 {"ok": true}
```

`issue_and_send(email)` (background, errors never reach the client):

```
user = store.find_by_email(email)          ; if None: return
code = new_code(); h = hash_code(secret, user.id, code)
resets.delete_expired(now); resets.issue(user.id, h, expires_at(now, minutes), now)
try:  mailer.send(user.email, *reset_mail(code, minutes))
except MailError:  resets.discard(user.id, h); log "reset mail failed user=<id> kind=<class>"
log "reset issued user=<id>"             # never the code, the address or the password
```

**`POST /api/auth/reset-password`**:

```
1. feature disabled                         -> 503 password_reset_unavailable
2. normalize_email / check_password fail    -> 422 invalid_email / invalid_password   (before any attempt is counted)
3. attempt_limiter.attempt(address) refused -> 429 too_many_reset_attempts, Retry-After (before any code is looked at)
4. code is not exactly 6 digits             -> 400 invalid_or_expired_code            (no database access)
5. user = find_by_email                     ; unknown: dummy compare, 400 invalid_or_expired_code
6. stored = resets.claim_attempt(user.id, now, max)   ; None: dummy compare, 400 invalid_or_expired_code
7. matches(stored, …) false                 -> 400 invalid_or_expired_code
8. resets.complete(user.id, stored, hasher.hash(password)) ; False -> 400 invalid_or_expired_code
9. login_limiter.clear(email); log "reset done user=<id> sessions_ended=<n>"
10. 204
```

The argon2 hash in step 8 happens only after the code matched. A `SQLAlchemyError` in steps 5–8 gives 503 `unavailable`.

**`GET /api/auth/options`** → `{"password_reset_enabled": settings.password_reset_enabled}`; public, no cookie needed.

**Limiters (`domain/resetlimit.py`)**: `ResetRequestLimiter.attempt(email, address) -> Decision`: first `SignupLimiter(max_per_address, 0, window).attempt(address)`, then `SignupLimiter(max_per_email, 0, window).attempt(normalized email)`; the first refusal wins and carries `Retry-After`. Unknown emails are counted exactly like known ones (AC-11). `ResetAttemptLimiter.attempt(address)` is one `SignupLimiter(max_tries_per_address, 0, window)` for step 3 (AC-17); a refusal records nothing. `0` switches a limit off.

## 5. SMTP adapter (`adapters/smtp_mailer.py`)

- `SmtpMailer(host, port, security, user, password, sender, timeout)`; `send(to, subject, body)` builds an `EmailMessage` (`From`, `To`, `Subject`, `Auto-Submitted: auto-generated`) and:
  - `starttls`: `SMTP(host, port, timeout=T)` → `starttls(context=ssl.create_default_context())` → `ehlo()` → `login` (when a user is set) → `send_message`.
  - `ssl`: `SMTP_SSL(host, port, timeout=T, context=…)` → `login` → `send_message`.
  - `none`: plain, no login; allowed only for loopback hosts.
- Every `OSError` (which includes `SMTPException` and timeouts) is wrapped in `MailError`; the message carries the exception class only, never the address, the code or the password.
- `smtp_security` and host are validated at startup: `none` with a non-loopback host, or a secret shorter than 32 characters, stops the API with a clear `ConfigError`.

## 6. Settings, compose, docs

- `config.py`: fields above plus `smtp_password: SecretStr | None` and `reset_code_secret: SecretStr | None` (names the loader treats as secret, so a value in the YAML is rejected). `password_reset_enabled` = `smtp_host` and `mail_from` and `reset_code_secret` all non-empty.
- `infra/config/newsdock.yaml` `api:` rows with the defaults; `infra/compose.yaml` api service passes `NEWSDOCK_SMTP_PASSWORD` and `NEWSDOCK_RESET_CODE_SECRET` from `.env` (empty default); `.env.example` documents both and says how to make the secret (`openssl rand -hex 32`).
- README section "Password reset by email": create a free Brevo account, verify one sender address, create an SMTP key, set `smtp_host: smtp-relay.brevo.com`, `smtp_port: 587`, `smtp_security: starttls`, `smtp_user` (the Brevo login), `mail_from`, and the two secrets **[Brevo settings: secondary sources]**; the same keys fit Gmail (`smtp.gmail.com`, app password) and Resend SMTP.

## 7. Web

- Routes `src/app/forgot-password/page.tsx`, `src/app/reset-password/page.tsx` (server components that render the forms, like `login`); `lib/gate.ts` adds both to `OPEN_PREFIXES`.
- `features/auth/ForgotPasswordForm.tsx`: email → `POST /api/auth/forgot-password` → on 202 show "If an account exists for that address, we sent a code" and a button to `/reset-password?email=…`; 422/429/503 messages.
- `features/auth/ResetPasswordForm.tsx`: email (prefilled), code (`inputMode="numeric"`, `autoComplete="one-time-code"`, 6 digits), new password (`autoComplete="new-password"`) → `POST /api/auth/reset-password` → on 204 "Password changed" with a link to `/login`; 400 "That code is wrong or has expired. Request a new one." with a link to `/forgot-password`; 422 password message from the existing `messages.ts`; 429/503 as above (a 429 on this screen reads "Too many attempts. Try again in …", using `formatWait`).
- `LoginForm` fetches `GET /api/auth/options` once; the link appears only when enabled (a failed request hides it).
- `messages.ts` gets `forgotMessage` and `resetMessage` next to `loginMessage`; styling uses the existing shadcn components and tokens (no hex, no palette classes).
- API types: add the routes to `openapi.json` and run `pnpm run generate:api`.

## 8. Security notes

- **Guessing:** a code is one of 10^6 values and gets at most 5 counted tries, so one issued code is guessed with probability at most 5·10⁻⁶; 3 issues per hour per email gives at most 1.5·10⁻⁵ an hour per account, and the per-address attempt limit (20 an hour) caps how many tries one client can make anywhere **[arithmetic, not a measurement]**.
- **Database leak:** rows hold keyed hashes; without `NEWSDOCK_RESET_CODE_SECRET` they cannot be brute-forced offline (ADR-0026).
- **Enumeration:** same status and body for known and unknown emails (AC-3); the foreground does the same work; refusals on reset are one 400.
- **Host-header or link injection:** none, the mail has no link.
- **CSRF:** the existing JSON-body and allowed-Origin guard applies to both POSTs.
- **Logs:** user id and outcome only.

## 9. Failure table (full)

| Failure | Where it shows | Result |
|---|---|---|
| Feature off | both routes | 503 `password_reset_unavailable`; `options` says false |
| Bad email format / weak password | request / reset | 422 |
| Limit hit | request / reset | 429 `too_many_reset_requests` / `too_many_reset_attempts` + `Retry-After` |
| SMTP error or timeout | background | code discarded, error logged, user still sees 202 |
| Database error | request path (limiter, schedule) | none: no database access in the foreground |
| Database error | background job | nothing stored or sent, error logged |
| Database error | reset | 503 `unavailable` |
| Two successes at once | reset | one wins; the other gets 400 |
| User deleted meanwhile | reset | the row is gone (cascade) → 400 |
| Clock moves back | reset | codes live a little longer; harmless |

## 10. Test seams (for `/spec-plan`)

- `FakeMailer` (records messages, can raise `MailError`, can block on an event) and an injectable clock for `now`; routes built with `create_app(..., mailer=, reset_clock=)`.
- AC-1 needs a real server (uvicorn thread, as the other live tests) because Starlette's `TestClient` finishes background tasks before returning.
- A small standard-library SMTP server (threaded socket, plain) exercises `SmtpMailer` for AC-2; STARTTLS/SSL ordering is unit-tested with a fake `smtplib` object.
- Docker tests use the `side_db` fixture only.
