# ui-login — Design

Status: design for review · 2026-10-27 · Spec: [spec.md](spec.md) · Detail: [design-detail.md](design-detail.md) · Diagrams: [diagrams/index.html](diagrams/index.html)

**Reading order:** this file → open the diagrams (each has a Check box) → answer the checklist at the bottom. `design-detail.md` is reference only (schemas, routes, failure table, security).

## Idea in four lines
- The **API owns identity**: `users` and `sessions` live in Postgres, passwords are argon2id, sessions are opaque ids stored as sha256 (ADR-0020).
- The **browser keeps calling the API directly**, now with credentialed CORS: explicit origins, `allow_credentials`, methods `GET,POST,PATCH,DELETE`. Cookies are host-scoped, so page and API must share a hostname (`localhost` or `127.0.0.1`); the web server redirects to the API's host when they differ (ADR-0021, replaces the proxy idea).
- **One resolver, three credentials**: session cookie (humans), `Bearer ndk_…` (agents), admin token (CLI). Routes then ask for a *role* or *an agent*; they never parse credentials themselves.
- The **live feed reuses the push-delivery wake-up** (`NOTIFY` → `WakeHub` → cursor query), with a session instead of a key.

## Components

New ids continue after C-9; C-6 (API) and C-8 (web) are extended.

| Id | Component | Job | Notes |
|---|---|---|---|
| C-10 | Accounts domain (`domain/accounts.py`) | roles, permission table, password policy, login-failure limiter | pure; no I/O |
| C-11 | Users and sessions repo (`adapters/users_repo.py`) | SQL for `users`, `sessions`; first-owner and last-owner locks | migration `0006` |
| C-12 | Principal resolver (`adapters/auth.py`, extended) | session cookie / agent key / admin token → one principal on `scope["state"]` | extends ADR-0016 middleware; rate limit unchanged for agents |
| C-13 | Account routes (`adapters/accounts_api.py`) | `/api/auth/{signup,login,logout,me}`, `/api/users*` | role guards as dependencies |
| C-14 | Live feed stream (`adapters/live.py`) | `GET /api/live` SSE for sessions | reuses `WakeHub`, `list_new`, cursor ids |
| C-15 | Web gate + API client (`src/proxy.ts`, `lib/api/client.ts`, host alignment in the root layout) | redirect cookie-less visitors to `/login`; every call uses `credentials: "include"`, `EventSource` uses `withCredentials`; redirect to the API's hostname when the page host differs | gate is optimistic only; the API decides |
| C-16 | Web screens (`features/{auth,users,agents,subscriptions,live}`) | login, signup, users, agents and keys, subscriptions, live feed | escaped text only |
| C-17 | Recovery route (`/api/admin/users/reset-password`) + `make user-reset-password` | set a user's password with the admin token; deletes that user's sessions | token only, never a session |
| C-6 | API (extended) | article reads need a principal; admin routes accept admin/owner session or token; CORS allows credentials and write methods | agent paths unchanged |
| C-8 | Web (extended) | `api_base_url` unchanged (what the browser calls); pages and API share a hostname | no ADR-0014 change |

## Key flows

- **F-5 Sign-up and login** (diagram 2): visitor → C-13 → C-11 (advisory lock decides owner vs viewer; argon2id hash) → `Set-Cookie` → UI.
- **F-6 Authorized read** (diagram 2): browser cookie (credentialed CORS) → C-12 resolves session (join `users`, role read every request) → route guard → data.
- **F-7 Agent and key management**: admin/owner session → `/api/admin/*` (same handlers as before) → key shown once.
- **F-8 Live feed** (diagram 4): session → C-14 starts at the newest `seq` → `NOTIFY` wakes → cursor query → SSE frames; every keep-alive tick re-checks the session.
- **Unchanged:** F-2 agent MCP flow, push-delivery streams (agent key only).

## Contracts

Routes (all JSON, errors `{"error": code}` or FastAPI `detail`):

| Route | Who | Result |
|---|---|---|
| `POST /api/auth/signup` | public, throttled | 201 `{user}`; 403 closed; 409 email taken; 422 policy |
| `POST /api/auth/login` | public, throttled | 200 `{user}` + cookie; 401 uniform; 429 + `Retry-After` |
| `POST /api/auth/logout` | session | 204, cookie cleared, row deleted |
| `GET /api/auth/me` | session | 200 `{id,email,role}`; 401 |
| `GET /api/users`, `PATCH /api/users/{id}` (role), `DELETE /api/users/{id}` | owner | 200/204; 409 last owner; 404 |
| `GET /api/articles*` | session or agent key | 200; 401 anonymous when `auth_required` |
| `/api/admin/*` (unchanged paths) | admin/owner session or admin token | as today; viewer 403 |
| `DELETE /api/admin/subscriptions/{id}` (new) | admin/owner session or admin token | 204; 404; the agent's open stream ends within one keep-alive |
| `POST /api/admin/users/reset-password` (C-17) | admin token only | 204; 404 unknown email; 422 policy; session 403 |
| `GET /api/live` | session (any role) | SSE; 401; 429 over per-user cap |
| `GET /api/health` | public | unchanged |

Tables (detail in design-detail §1): `users(id, email unique lower, password_hash, role, created_at)`, `sessions(token_hash pk, user_id fk cascade, created_at, last_seen_at, expires_at)`. Role is a text column with a CHECK in (`owner`,`admin`,`viewer`).

Settings (flat keys in `api:`, defaults in code): `auth_signup_open` true, `auth_password_min_length` 10, `auth_session_idle_hours` 12, `auth_session_absolute_days` 7, `auth_login_max_failures` 5, `auth_login_window_minutes` 15, `auth_cookie_secure` false, `live_max_streams_per_user` 3. Web: no setting changes. CORS: `cors_allow_credentials` true, `cors_allow_methods` `GET,POST,PATCH,DELETE`, `cors_allow_headers` `Content-Type,Last-Event-ID` (explicit, no `*`), `cors_origins` unchanged.

## Tricky parts

- **First owner under concurrency (AC-2):** sign-up runs in one transaction that first takes `pg_advisory_xact_lock(<const>)`; inside it `role = owner` iff no user exists. Same lock guards role change and delete, so the last owner cannot be removed by two racing requests (AC-10).
- **No account enumeration or timing leak (AC-5):** unknown email verifies against a fixed dummy argon2 hash; the response body is identical.
- **Login throttle (AC-13):** in-memory failure counter per normalized email (one API worker, same assumption as the agent limiter); success clears it. Per-IP keys are weak (shared NAT, local use), so the key is the account. A locked account can be locked out by an attacker for one window: accepted, documented.
- **Sessions:** cookie holds 32 random bytes (base64url); DB holds sha256. Role and existence are read on every request, so demotion or deletion applies at once. `last_seen_at` is updated at most once a minute. Expired rows are removed at login and by a periodic delete in the API process.
- **CSRF with credentialed CORS:** cookie is `SameSite=Lax`; state-changing routes require `Content-Type: application/json` (415 otherwise, so a plain form post cannot carry a body); the API rejects a non-GET whose `Origin` is present and not in `cors_origins`; only listed origins get `Access-Control-Allow-Credentials`. Another local app on a different port is same-site, so the Origin check is the real guard, not Lax.
- **Hostname alignment:** the cookie is stored for the host the browser used to reach the API (no port). A page on `localhost:3000` calling `127.0.0.1:8000` is cross-site and gets no cookie. The root layout (which already reads runtime config) redirects to the same path on `api_base_url`'s hostname when the request host differs.
- **EventSource:** `new EventSource(url, {withCredentials: true})`; the browser resends `Last-Event-ID` on reconnect, which is why that header is in the CORS allow list.
- **Dev mode (`auth_required=false`):** article reads and the live feed stay open and the UI shows no gate; `/api/admin/*` and `/api/users*` still need a principal (opening management would defeat roles). Refines spec §8.

## Top failure modes

| Failure | Effect | Handling |
|---|---|---|
| Postgres down | no auth possible | 503 `unavailable` (as agent auth does) |
| API down | browser fetch fails | UI shows a retry notice (no silent redirect to `/login`) |
| Cookie lost / expired | 401 mid-use | UI redirects to `/login` and returns to the page after login |
| Listener outage | live feed stalls | fallback poll every `sse_fallback_poll_seconds`, as agent streams |
| Owner locked out (forgot password) | no admin UI | `make user-reset-password EMAIL=<email>` (C-17, AC-16) |

## Technology

`argon2-cffi` 25.1.0 **[verified 2026-10-27, PyPI: current release, requires Python ≥3.8]** (the library behind most Python argon2 use, not yet in the lockfile); Starlette `Response.set_cookie` and `CORSMiddleware` for cookies and credentialed CORS; Next.js 16.3.8 `proxy.ts` (renamed middleware) **[verified: Next docs in node_modules]**; existing SQLAlchemy 2 / Alembic, `WakeHub`, `FixedWindowLimiter`. No JWT, no auth framework, no Redis.

## AC coverage

| AC | Covered by |
|---|---|
| AC-1, AC-3 | C-10 policy, C-11, C-13 signup |
| AC-2, AC-10 | C-11 advisory lock, C-13 users routes |
| AC-4, AC-5, AC-6 | C-13 login/logout/me, C-11 sessions, C-12 expiry |
| AC-7 | C-12 + article route guard (C-6) |
| AC-8 | C-15 gate, C-16 login page |
| AC-9, AC-14 | C-12 principal, C-10 permission table, admin dependency |
| AC-11, AC-12 | C-16 agents/subscriptions screens over existing `/api/admin/*` |
| AC-13 | C-10 login limiter, C-13 |
| AC-15 | C-14 + C-15 (`withCredentials`) + C-16 live page |
| AC-16 | C-17 recovery route + make target |

## Questions to answer before approving this design

- [x] Accept ADR-0020 (API-owned users and DB sessions, argon2id, roles as a column)? Accepted 2026-10-27 (bundle A after the user asked to review alternatives).
- [x] ADR-0021: credentialed CORS instead of a proxy. Accepted 2026-10-27 (user choice).
- [x] Split "viewer reads, admin manages agents, owner manages users". Confirmed 2026-10-27.
- [x] Defaults 12 h idle / 7 d absolute, 5 failures per 15 min, min password 10. Confirmed 2026-10-27.
- [x] Live feed starts at "now", no backlog. Confirmed 2026-10-27.
- [x] Locked-out owner recovers with `make user-reset-password` (adds C-17 and AC-16). Chosen 2026-10-27.
