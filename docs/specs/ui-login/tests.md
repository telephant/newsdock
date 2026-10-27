# ui-login — Tests

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Plan: [plan.md](plan.md)

**Fixtures:** no GDELT data. Domain and web unit tests use fakes (in-memory user/session stores, fake hasher, fake clock, mocked `fetch`/`EventSource`). API integration tests reuse the existing harness in `apps/api/tests/integration` (real Postgres through compose project `newsdock-login-test`, live uvicorn on a free port, `pytestmark = pytest.mark.docker`, run with `make test-infra SCENE=api`). Articles for read and live tests are inserted directly with SQL like `test_stream_api.py`. Test passwords are fixed strings that must never appear in logs (TC-4). Web tests: vitest + Testing Library under `apps/web/src/**.test.tsx`.

| TC | AC | Level | Case (Given / When / Then) |
|---|---|---|---|
| TC-1 | AC-1 | integration | Given sign-up open and no `a@x.io`; When `POST /api/auth/signup {email, password}`; Then 201, a row with role `viewer` (a prior owner exists), `password_hash` starts with `$argon2id$` and is not the plaintext, and the response JSON has no `password*` field |
| TC-2 | AC-1 | unit | `Argon2Hasher`: `hash()` yields an argon2id PHC string, `verify()` is true for the right and false for a wrong password and for garbage hashes (no exception), `needs_rehash()` is true for weaker parameters |
| TC-3 | AC-1 | integration | Migration 0006: upgrade creates `users`, `sessions`; role CHECK rejects `root`; unique email rejects a duplicate; deleting a user cascades its sessions; downgrade drops both and leaves `agents`, `api_keys`, `subscriptions` intact |
| TC-4 | AC-1 | integration | Given log capture at DEBUG; When sign-up, login, logout and reset run with known passwords; Then no log record contains a password, the session cookie value, a token hash, an argon2 hash or the admin token (NFR-1) |
| TC-5 | AC-2 | integration | Given an empty `users`; When 8 threads call `create_user` at once, repeated 20 times with a clean table each round; Then every round has exactly one `owner` and the rest `viewer` |
| TC-6 | AC-3 | unit | Policy: email trimmed and lower-cased, malformed or >254 chars rejected; password shorter than `auth_password_min_length` or longer than 128 rejected; `signup_open=false` yields `SignupClosed` |
| TC-7 | AC-3 | integration | Given `a@x.io` exists; When sign-up repeats with `A@X.IO ` (409), a 9-char password (422), a 129-char password (422), a bad email (422), and, with `auth_signup_open=false`, a fresh email (403); Then the status is as listed and the row count is unchanged |
| TC-8 | AC-4 | integration | Given `a@x.io`; When login with the right password; Then 200, `Set-Cookie` has `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age` = absolute lifetime and no `Secure` (setting off; with `auth_cookie_secure=true` it has `Secure`), and `GET /api/auth/me` with that cookie returns `{id,email,role}` |
| TC-9 | AC-4 | integration | CORS with the real app: preflight `OPTIONS /api/auth/login` from `http://localhost:3000` (listed) answers `Allow-Origin` = that origin, `Allow-Credentials: true`, methods include `POST`, `PATCH`, `DELETE`, headers include `Content-Type` and `Last-Event-ID`; an unlisted origin gets no `Allow-Origin`; no response ever sends `*` with credentials. Replaces the GET-only cases in `tests/unit/test_cors.py` |
| TC-10 | AC-4 | integration | Write routes: `POST /api/auth/login` with `Content-Type: text/plain` → 415; with `Origin: http://evil.example` → 403 `bad_origin`; with a listed Origin or no Origin → accepted; `GET /api/articles` with a foreign Origin is not blocked by this check (CORS alone governs it) |
| TC-11 | AC-5 | unit | `verify_login` with a fake hasher: for an unknown email the hasher's `verify` is still called once (against the dummy hash) and the result is `InvalidCredentials`; for a known email with a wrong password the same exception type and message |
| TC-12 | AC-5 | integration | Given `a@x.io`; When login with a wrong password for it and any password for unknown `b@x.io`; Then both 401 with byte-identical bodies and `sessions` has no new row |
| TC-13 | AC-6 | unit | `session_valid(now, last_seen_at, expires_at, idle)` (the absolute lifetime is carried by `expires_at = session_expiry(created, absolute)`): valid inside both limits; invalid after idle; invalid after `expires_at`; boundary instants; touch is skipped when `last_seen` is under 60 s old |
| TC-14 | AC-6 | integration | Given a session cookie; When `POST /api/auth/logout`; Then 204, `Set-Cookie` with `Max-Age=0`, the `sessions` row is gone, the old cookie gets 401 on `/api/auth/me` and `/api/articles`; a second logout is 204 |
| TC-15 | AC-6 | integration | Given a session; When `last_seen_at` is moved beyond the idle limit, and in a second case `expires_at` into the past; Then each gets 401 on `/api/auth/me` and `/api/articles` and the expired row is deleted by the next login of that user |
| TC-16 | AC-7 | integration | Given `auth_required=true` and one article; When `GET /api/articles` and `/api/articles/{id}` are called anonymously, with a viewer session, with a valid agent key, with a revoked key and with a forged cookie; Then 401, 200, 200, 401, 401; `GET /api/health` is 200 anonymously; with `auth_required=false` anonymous reads are 200 |
| TC-17 | AC-7 | integration | Regression (NFR-3): the existing `test_auth_api.py`, `test_mcp_api.py`, `test_stream_api.py` and unit suites pass unchanged except the deliberate edits to the article-read and CORS tests |
| TC-18 | AC-8 | unit | Gate (`proxy.ts` function): no `newsdock_session` cookie on `/` → redirect to `/login?next=%2F`; the cookie present → pass; `/login`, `/signup`, `/_next/*`, `/favicon.ico` pass without a cookie |
| TC-19 | AC-8 | unit | API client: every call sends `credentials: "include"`, JSON bodies carry `Content-Type: application/json`, a 401 on a data call navigates to `/login?next=<path>`, a 401 on `/api/auth/login` does not, a network error returns a typed `unreachable` result and does not redirect |
| TC-20 | AC-8 | unit | Host alignment: request host `localhost:3000` with `apiBaseUrl` `http://127.0.0.1:8000` → redirect to `http://127.0.0.1:3000/<path>`; equal hosts → none; non-loopback mismatch (`app.example`, `api.other`) → configuration error naming both hosts |
| TC-21 | AC-8 | unit | Login form: success navigates to `next` (default `/`), 401 shows one generic message, 429 shows the retry time from `Retry-After`; signup form: 409, 422 and 403 `signup_closed` show their messages, success goes to `/login`; messages are text nodes |
| TC-22 | AC-8 | manual | See checklist M-1 |
| TC-23 | AC-9 | unit | `PERMISSIONS`: `read_articles` and `live_feed` allow viewer/admin/owner; `manage_agents` allows admin/owner; `manage_users` allows owner only; an unknown permission raises |
| TC-24 | AC-9 | integration | Given a viewer, an admin and an owner session; When each calls `GET /api/admin/agents` and `GET /api/users`; Then viewer 403/403, admin 200/403, owner 200/200; an agent key gets 403 on both and anonymous 401 on both, also with `auth_required=false` |
| TC-25 | AC-9 | unit | Navigation: viewer sees Feed and Live only; admin adds Agents and Subscriptions; owner adds Users; `me` loading shows no admin links; a 401 `me` redirects to `/login` |
| TC-26 | AC-10 | integration | Given an owner O and viewer V; When O promotes V to admin, then O demotes O, then O deletes O; Then 200, 409 `last_owner`, 409 `last_owner`; with two owners both demoting each other in parallel (20 rounds) at least one owner always remains; deleting V removes V's sessions |
| TC-27 | AC-10 | unit | Users screen: lists users with a role select; changing a role calls `PATCH`; a 409 shows "last owner" and reverts the select; delete asks for confirmation; emails are text nodes |
| TC-28 | AC-11 | unit | Agents screen: create shows the `api_key` once with a copy button, re-render or navigation hides it, the list never shows secrets; revoke calls `DELETE …/keys/{id}`; disable/enable call their routes; a hostile agent name `<img onerror>` renders as text |
| TC-29 | AC-11 | manual | See checklist M-2 |
| TC-30 | AC-12 | integration | Given two agents each with a subscription; When an admin session calls `GET /api/admin/subscriptions` then `DELETE /api/admin/subscriptions/{id}` for one; Then both rows listed with agent names, 204, the list has one row, the deleted subscription's stream request is 404 and an already open stream ends within 2×keep-alive; viewer 403; unknown id 404; the admin token also works |
| TC-31 | AC-12 | unit | Subscriptions screen: rows show agent name and filter fields, delete calls the API and removes the row, filter text is escaped |
| TC-32 | AC-13 | unit | `LoginLimiter` with a fake clock: allows N−1 failures, blocks at N with `retry_after` = time left, window expiry resets, success clears, accounts are independent, keys are case-normalized, memory is bounded (old entries pruned) |
| TC-33 | AC-13 | integration | Given `auth_login_max_failures=3`, window 60 s; When 3 wrong logins for `a@x.io` then the right password; Then 429 with `Retry-After`; `b@x.io` still logs in; after the window (setting 1 s in the test) the right password works |
| TC-34 | AC-13 | unit | Settings: new keys exist with the documented defaults and the rows in `infra/config/newsdock.yaml` equal them (`make config-python` green; unknown-key and differs-from-default checks pass) |
| TC-35 | AC-14 | integration | Given `NEWSDOCK_ADMIN_TOKEN` set; When `GET /api/admin/agents` with the token and no cookie, with a wrong token, with an agent key; Then 200, 401, 403; the token on `GET /api/users` and on `POST /api/auth/logout` is 401; with no token configured the admin routes answer 404 as today |
| TC-36 | AC-15 | integration | Given a logged-in viewer with `/api/live` open and existing articles in the table; When no new row exists, then a row is committed; Then no backlog event arrives first, one `event: article` with `id` = `encode_cursor(seq)` arrives within a few seconds; reconnect with `Last-Event-ID` returns exactly the rows after it; anonymous → 401; a malformed id → 400; the (cap+1)th stream of one user → 429; logout ends the open stream within 2×keep-alive; filter `domain=` only passes matching rows |
| TC-37 | AC-15 | integration | Regression for the factored SSE loop: every case of `test_stream_api.py` (agent streams: filter, resume, keep-alive, revocation, cap, fallback poll) passes unchanged |
| TC-38 | AC-15 | unit | Live page: opens `EventSource` with `withCredentials: true`, prepends each event, escapes titles (`<script>` as text), closes the source on unmount, shows a reconnecting state on error |
| TC-39 | AC-15 | manual | See checklist M-3 |
| TC-40 | AC-16 | integration | Given `a@x.io` with a session and the admin token configured; When `POST /api/admin/users/reset-password` with the token, then with an admin session, then with an owner session; Then 204, 403, 403; the old password and old session get 401, the new password logs in; unknown email 404; weak password 422; no token configured 404 |
| TC-41 | AC-16 | unit | `make user-reset-password` script: with a fake `curl` and `read -s` input on stdin the new password is never in curl's argv or the printed output, a missing `EMAIL` or `.env` or token exits non-zero with usage |
| TC-42 | AC-4, AC-15 | spike (done 2026-10-27, passed; findings in plan.md Progress) | T-01: argon2-cffi measured on the dev machine; real uvicorn answers a credentialed preflight with `Last-Event-ID`; in a real browser a page on `localhost:3000` logs in against `localhost:8000`, gets the cookie, and an `EventSource` with credentials connects (result recorded in plan.md Progress) |

## Manual checklists

**M-1 (AC-8, TC-22)** with `make up`, no accounts:
1. Open `http://localhost:3000` (compose default API is `127.0.0.1`): the browser lands on `http://127.0.0.1:3000/login?next=/` (host alignment).
2. Sign up as `owner@example.test`: the account is the owner (Users link visible). Log out. Sign up a second account: viewer, no admin links.
3. Open `/` in a private window: redirected to `/login`. Log in as the viewer: the article list appears.
4. Stop the API container: the feed shows a retry notice, not the login page. Start it again.

**M-2 (AC-11, TC-29)** as an admin:
1. Agents → create `demo-x`: the key appears once; copy it; reload: the key is gone.
2. Call `/mcp` (MCP client or curl initialize) with the key: accepted. Revoke the key in the UI: the same call returns 401.
3. Disable and enable the agent: the screen reflects it.

**M-3 (AC-15, TC-39)**:
1. Log in, open `/live`; leave it open.
2. With the stack running, wait for the next ingest slot (or insert a test row with SQL): the article appears without a reload.
3. Log out in another tab: the live page's stream ends within about 15 s and the page shows the signed-out state.
4. `curl -N http://127.0.0.1:8000/api/live` returns 401.

## Measurements (provisional targets, not pass/fail)

| Id | What | How |
|---|---|---|
| M-a | argon2 time per hash and per failed login | `time` 20 hashes with the default `PasswordHasher` parameters in T-01; record median and p95; tune parameters only with the user's approval |
| M-b | Unknown-email vs wrong-password response time gap | 200 requests each against the real app; record the median difference (target: no systematic gap beyond noise) |
| M-c | Insert → live event latency | TC-36 timestamps from commit to frame, 20 samples with the real listener; record median and max (expect well under `sse_keepalive_seconds`) |
| M-d | Default lifetimes and limit (12 h idle, 7 d absolute, 5 per 15 min, min password 10) | not measurable; confirmed by the user at /spec-design, kept as settings |

## Coverage

Every AC-1…AC-16 has at least one TC above (checked by grep in plan.md "Plan validation"); TC-22, TC-29, TC-39 are the manual ACs (AC-8, AC-11, AC-15); TC-42 is the spike.
