# ui-login — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation (2026-10-27)

| # | Check | Method | Result |
|---|---|---|---|
| 1 | AC → test coverage | awk over the AC column of tests.md | **pass**: AC-1…AC-16 each have ≥ 1 TC (counts 4,1,2,4,2,3,2,5,3,2,2,2,3,1,5,2); 42 TCs, none without an AC, numbering has no gaps |
| 2 | AC → design / task coverage | grep design.md; `Implements:` lines in tasks/ | **pass**: 16/16 in design.md and in ≥ 1 task |
| 3 | TC ↔ task links | grep TC ids in tasks/ against tests.md | **pass**: no undefined TC in a task, no TC without a task |
| 4 | Cross-doc names | `auth_signup_open`, `auth_required`, `newsdock_session`, `/api/live`, `/api/admin/users/reset-password`, `DELETE /api/admin/subscriptions/{id}`, `delete_any`, `latest_seq`, `last_owner`, `bad_origin` across spec/design/tests/tasks | **fixed**: spec used `auth.signup_open` / `auth.required` while config keys are flat (`auth_signup_open`, `auth_required`); renamed in spec. **Found at planning:** design had no admin route to delete a subscription although AC-12 and the scope need it; added to design.md and design-detail.md (T-06). Diagrams unchanged (component diagram shows C-6 admin routes generically) |
| 5 | Proposed ADRs treated as decided | ADR-0020, ADR-0021 | **pass**: both Accepted 2026-10-27 |
| 6 | Untagged claims / invented numbers / glossary | 128, 254, 60 s, cap 3, lock constant | **fixed**: added to spec provisional targets (128/254 input bounds, 60 s touch interval, 3 live streams per user); the advisory-lock key is an implementation constant, not a requirement. Glossary gained CORS, CSRF, Origin check, Principal, Hostname alignment, Advisory lock |
| 7 | Scope leaks from backlog.md | grep invites, MFA, OAuth, audit, webhook | **pass**: only under "Out of scope" / extension points |
| 8 | Open questions / unchecked items | grep `- [ ]` in spec and design | **pass**: none; all design checklist items ticked with dates |

Findings carried as risks (none block the plan):
- **R-1 (resolved 2026-10-27 by T-01, Chrome only)** Cross-port cookies, `EventSource` with credentials and `Last-Event-ID` in CORS all work with a hostname-aligned page and API. Residual: Safari and Firefox untested (**[memory]**); M-1 and M-3 should be repeated in one of them if available.
- **R-2 (medium)** T-05 changes the shared auth middleware and T-09 factors the agent SSE loop; the agent suites (TC-17, TC-37) are the guard and must stay unchanged.
- **R-3 (low)** Open sign-up (D-3) is the user's choice against the recommendation; documented in the README in T-14, switchable with `auth_signup_open`.
- **R-4 (low)** Login throttle is in memory and per account (one API worker); a locked account can be locked out by an attacker for one window.
- **R-5 (low)** `make check` flagged the loop's `.claude/` lock before the layout fix on `main`; the fix is in this branch's base, so no known exception remains.

**Verdict: GO.** `gates.plan: approved`. No `design-review.md` exists, so nothing to retire.

## Spike first

**T-01** de-risks what the design leans on without evidence: (1) argon2-cffi parameters and timing on this machine (M-a, also adds the dependency to the lockfile), (2) that Starlette's CORS middleware yields the credentialed preflight headers including `Last-Event-ID`, and (3) that a real browser on `localhost:3000` stores and sends the API's cookie for `fetch` and `EventSource` with credentials. (3) is the choice ADR-0021 stands on; a "no" sends the project back to the proxy option before any code depends on it.

## Phases and milestones

| Phase | Tasks | Milestone (ACs) | Effort |
|---|---|---|---|
| 0 Spike | T-01 | claims verified | 0.5 d |
| 1 Core | T-02, T-03 | domain rules, tables, owner locks (AC-2; support for AC-3, AC-5, AC-9, AC-10, AC-13) | 1.5 d |
| 2 Accounts API | T-04, T-05, T-07 | AC-1, AC-3…AC-7, AC-13, AC-14 (API side) | 2 d |
| 3 Roles and admin | T-06, T-08 | AC-9, AC-10, AC-12, AC-16 (API side) | 1.5 d |
| 4 Live | T-09 | AC-15 (API side) | 1 d |
| 5 Web | T-10, T-11, T-12, T-13 | AC-8…AC-12, AC-15 (UI side) | 3 d |
| 6 Close | T-14 | manual runs, docs, status | 1 d |

## Definition of Done (every task)

Tests first and red→green; `make check` green; `make test APP=api` or `APP=web` for the touched app; `make test-infra SCENE=api` (and `db` for the migration) where a task names it; `make config-python` green when a setting is added; documentation that repeats a changed fact updated in the same edit; no secrets, passwords or session values in code, docs or logs; new routes added to the OpenAPI file and web types regenerated (T-10 onward); one commit per task on this branch.

## Tasks

| Task | Title | Implements | Depends on |
|---|---|---|---|
| T-01 | Spike: argon2, credentialed CORS, cross-port cookie | AC-4, AC-15 (risk) | none |
| T-02 | Domain: roles, policy, limiter, session validity | AC-3, AC-5, AC-9, AC-13 | T-01 |
| T-03 | Migration 0006 and users/sessions repo | AC-1, AC-2, AC-10 | T-02 |
| T-04 | Settings, argon2 adapter, sign-up and login | AC-1, AC-3, AC-4, AC-5, AC-13 | T-03 |
| T-05 | Principal resolver, expiry, read guard, logout, me | AC-4, AC-6, AC-7, AC-14 | T-04 |
| T-06 | Role guards, users routes, admin by session, subscription delete | AC-9, AC-10, AC-12, AC-14 | T-05 |
| T-07 | Credentialed CORS settings | AC-4, AC-15 | T-04 |
| T-08 | Reset-password route and make target | AC-16 | T-05 |
| T-09 | Live feed endpoint and shared SSE loop | AC-15 | T-05 |
| T-10 | Web foundation: types, client, gate, host alignment | AC-8 | T-06, T-07, T-09 |
| T-11 | Web auth pages and navigation | AC-8, AC-9 | T-10 |
| T-12 | Web users, agents, subscriptions screens | AC-10, AC-11, AC-12 | T-10, T-06 |
| T-13 | Web live feed page | AC-15 | T-10, T-09 |
| T-14 | Docs, config rows, manual runs, status | AC-8, AC-11, AC-15 (manual), all | T-01…T-13 |

## Progress

- [x] **T-01** Spike (2026-10-27) — passed, no design change.
  - argon2-cffi 25.1.0 added to `apps/api/pyproject.toml` and `uv.lock`. Defaults (argon2id v19, t=3, m=64 MiB, p=4): hash median 22.5 ms / p95 23.7 ms; verify ok 22.9 / 24.3 ms; verify wrong 23.6 / 24.5 ms (M-a). Far below the 200 ms target.
  - Credentialed CORS with real uvicorn + Starlette: a listed origin gets `Allow-Origin` (echoed, never `*`), `Allow-Credentials: true`, methods `GET, POST, PATCH, DELETE`, headers incl. `Content-Type`, `Last-Event-ID`; an unlisted origin's preflight is 400 with no `Allow-Origin`.
  - Real browser (headless Chrome, throwaway page on :3000 and API on :8000, files kept out of the repo): page `http://localhost:3000` → API `http://localhost:8000`: login 200, cookie stored, `fetch` with credentials 200, `EventSource` with credentials connected with the cookie, and after the server closed the stream the browser reconnected by itself sending `Last-Event-ID: 1`, which the server saw. Page `http://localhost:3000` → API `http://127.0.0.1:8000`: login 200 but the next `fetch` got 401 and the stream request carried no cookie, confirming that host alignment (design C-15) is needed.
  - Not covered: Safari and Firefox; production `Secure` cookies over HTTPS.
- [x] **T-02** Domain (2026-10-27) — TC-6, TC-11, TC-13, TC-23, TC-32 green (37 tests in `test_accounts.py`, `test_loginlimit.py`); `make check-python` green (405 passed, mypy strict, import-linter 4 kept).
  - `domain/accounts.py`: `Role`, `PERMISSIONS`, `can`, `normalize_email`, `check_password`, `ensure_signup_open`, `StoredUser`, `PasswordHasher`/`UserLookup` protocols, `verify_login` (dummy-hash equal work, also for malformed emails), `session_expiry`, `session_valid`, `should_touch`. `domain/loginlimit.py`: `LoginLimiter` (window opens at first failure and is not extended, success clears, pruning plus a hard entry cap).
  - Deviation from the task text, no design change: `session_valid` takes `(now, last_seen_at, expires_at, idle)`; `created_at` is not needed because `expires_at` already holds the absolute limit.
- [x] **T-03** Migration 0006 and users/sessions repo (2026-10-27) — TC-3, TC-5 and the repo halves of TC-15 and TC-26 green on real Postgres: `test_users_repo.py` 12 passed; `make test-infra SCENE=api` 72 passed; `SCENE=db` 4 passed (idempotent upgrade, no autogenerate drift); `make check-python` green (405 unit).
  - `infra/migrations/versions/0006_users_sessions.py`, ORM `User` and `UserSession` in `packages/db/.../models.py`, `adapters/users_repo.py` (`SqlUsersRepo`), domain types `DuplicateEmail`, `LastOwner`, `UserSummary`, `SessionInfo` in `domain/accounts.py`; `packages/db/tests/unit/test_metadata.py` now lists the two tables.
  - One advisory lock (`USERS_WRITE_LOCK = 7_041_001`) guards create_user, set_role and delete_user. Mutation check: with the lock disabled the three race tests fail (first-owner, demote-each-other, delete-each-other), so they do guard it.
  - Choices inside the design: the repo exposes `delete_expired(now, idle)` (absolute and idle expiry in one statement); `set_password_hash` was added in T-04 (login rehash; T-08 reuses it).
- [x] **T-04** Settings, argon2 adapter, sign-up and login (2026-10-27) — TC-1, TC-2, TC-4 (sign-up and login part), TC-7, TC-8 (cookie half), TC-12, TC-33, TC-34 green: 9 new unit tests (`test_passwords.py`, `test_config.py`), 12 new Docker tests (`test_accounts_api.py`) plus 1 (`set_password_hash`) in `test_users_repo.py`; `make check-python` 414 passed, `make config-python` green, `make test-infra SCENE=api` 85 passed. Mutation check: logging the password makes the log test fail.
  - New: `adapters/passwords.py` (`Argon2Hasher`, `make_dummy_hash`), `adapters/accounts_api.py` (`POST /api/auth/signup`, `POST /api/auth/login`), `domain/accounts.py` (`AccountStore`, `new_session_token`, `hash_token`), settings and yaml rows, `create_app(users_repo, hasher, login_limiter)` injection points, `SqlUsersRepo.set_password_hash`.
  - Deviations, no design change: (1) the setting is `auth_min_pw_length` (the config loader rejects keys containing "password"); renamed in design.md, tests.md and the task file. (2) `cors_allow_cookies` and `live_max_streams_per_user` are added in T-07 and T-09, where they are used, not here. (3) `/me` in TC-8 and the logout/reset log checks of TC-4 belong to T-05 and T-08 (tests.md notes it).
  - Error codes in `detail`: `signup_closed` 403, `invalid_email` / `invalid_password` 422, `email_taken` 409, `invalid_credentials` 401, `too_many_attempts` 429 (+ `Retry-After`), `unavailable` 503.
- [x] **T-05** Principal resolver, session expiry, read guard, logout and me, Origin and JSON checks (2026-10-27) — TC-8 (/me), TC-10, TC-14, TC-15, TC-16, TC-17, TC-35 (token half), TC-4 (logout part) green: 12 unit (`test_principal.py`) + 16 Docker (`test_session_api.py`) + 2 agent unit; `make check-python` 426 passed; `make config-python` green; `make test-infra SCENE=api` 101 passed, so every existing agent-path suite (auth, MCP, subscriptions, streams) is unchanged. Mutation check: disabling the read guard and the Origin check fails 8 session tests.
  - New: `adapters/principal.py`, `GET /api/auth/me`, `POST /api/auth/logout`, read guard on `GET /api/articles*`, app-wide write guard, `AccountStore` now includes `SessionStore`.
  - Deviation, recorded in design.md C-12 and design-detail §2: the resolver runs as FastAPI dependencies, not in `AuthMiddleware`, because that middleware sits outside CORS and its 401s would be unreadable to the credentialed UI (a test asserts the 401 carries `Access-Control-Allow-Origin`).
  - Side effect handled: `export_labels` read `/api/articles` anonymously and now sends `NEWSDOCK_AGENT_API_KEY` (2 unit tests). Other known anonymous readers: the web UI (T-10 switches it to cookies) — until T-10 the live UI feed gets 401 when `auth_required` is true.
- [x] **T-06** Role guards, users routes, admin by session, subscription delete (2026-10-27) — TC-24, TC-26, TC-30, TC-35 green: 13 Docker tests (`test_roles_api.py`); `make check-python` 428 passed; `make config-python` green; `make test-infra SCENE=api` 114 passed. Mutation check: letting `manage_users` use the `manage_agents` permission fails the matrix and error tests.
  - New: `Guards.admin` and `Guards.manage_users`, `build_users_router` (`GET /api/users`, `PATCH /api/users/{id}`, `DELETE /api/users/{id}`; 409 `last_owner`, 404 `not_found`), `DELETE /api/admin/subscriptions/{id}` with `SubscriptionStore.delete_any`, `UserAdminStore` and `UsersStore` protocols; `build_admin_router(registry, subscriptions, require_admin)` no longer takes the token.
  - Behaviour change, recorded in the ADR-0016 amendment: with no admin token configured the admin routes are no longer hidden with 404 (sessions manage agents without a token); they answer 401 without a principal. Three older unit tests changed accordingly (`test_admin.py` x2, `test_subscriptions_api.py`), and a key-shaped but unregistered credential is now 401, a registered agent key still 403.
  - Not covered here: an open agent stream ending after an admin delete is relied on from push-delivery's existing keep-alive re-check (`subscriptions.exists`, its TC-11); the route test asserts the stream request is 404 right after the delete.
- [x] **T-07** Credentialed CORS settings (2026-10-27) — TC-9 green: `test_cors.py` rewritten (23 unit cases incl. both listed origins, `PATCH`/`DELETE`/`Last-Event-ID` preflights, unlisted origin, no `*`, setting off, write from an unlisted origin); `make check-python` 438 passed; `make config-python` green; `make test-infra SCENE=api` 114 passed.
  - Changed defaults: `cors_allow_methods` `GET,POST,PATCH,DELETE`, `cors_allow_headers` `Content-Type,Last-Event-ID`; new `cors_allow_cookies` (true) passed to `CORSMiddleware(allow_credentials=…)`; rows added to `infra/config/newsdock.yaml`.
  - Deviation: the setting is `cors_allow_cookies`, not `cors_allow_credentials` (the config loader rejects keys containing "credential"); renamed in design.md and the task files.
  - Finding: Starlette prints `Access-Control-Allow-Credentials: true` even in answers to an unlisted origin, but never an `Allow-Origin`, so no browser grants anything; the test asserts the real property (no `Allow-Origin`). The T-01 spike saw the same on the preflight 400.
- [x] **T-08** Owner recovery: reset-password route and make target (2026-10-27) — TC-40, TC-41 and the reset part of TC-4 green: 8 Docker tests (`test_reset_password.py`), 9 script tests (`test_user_reset_password.py`); `make check-python` 447 passed; `make config-python` green; `make test-infra SCENE=api` 122 passed. Mutation check: letting a session through the token-only guard fails `test_sessions_cannot_reset_passwords`.
  - New: `POST /api/admin/users/reset-password` (`build_recovery_router`, `Guards.admin_token_only`: 404 when no token is configured, 403 for a session or agent key, 401 for nobody; 204 / 404 unknown email / 422 policy), `infra/scripts/user_reset_password.sh`, Makefile target `user-reset-password`, README row, `AccountStore.delete_user_sessions`.
  - The password is read with `read -s` twice, JSON-encoded through stdin and sent as the request body; the admin token goes through a mode-600 header file (`curl -H @file`), so neither appears in argv, output or logs (the fake-curl test asserts it with a password full of quotes, backslashes, unicode and shell characters).
  - Addition within the intent of D-9: a reset also clears the login-failure counter for that email, because the typical user of this route is a locked-out owner (test: locked out by 3 failures, reset, logs in).
  - Test detail: `infra/scripts/tests/test_user_reset_password.py` uses a minimal `PATH` instead of `os.environ` (rule DR-9); `RESET_ROOT` overrides the repo root for the script, like `DOCTOR_ROOT`.
