# ui-login — Design detail

Reference only; not required reading for approval. Overview: [design.md](design.md). Tags: **[verified]** checked 2026-10-27, **[memory]**, **[assumption]**.

## 1. Schema (migration `infra/migrations/versions/0006_users_sessions.py`)

```
users
  id            uuid pk (server default gen_random_uuid())
  email         text not null            -- stored lower-cased and trimmed
  password_hash text not null            -- argon2id PHC string
  role          text not null check (role in ('owner','admin','viewer'))
  created_at    timestamptz not null default now()
  unique index users_email_key on (email)

sessions
  token_hash    text pk                  -- sha256 hex of the cookie value
  user_id       uuid not null references users(id) on delete cascade
  created_at    timestamptz not null default now()
  last_seen_at  timestamptz not null default now()
  expires_at    timestamptz not null     -- created_at + absolute lifetime
  index sessions_user_idx on (user_id)
  index sessions_expires_idx on (expires_at)
```

The sink's 7-day retention does not touch these tables. `agents` and `api_keys` are unchanged; agents are not owned by users in this milestone (an admin sees all agents) **[assumption]**.

## 2. Principal resolution (C-12)

Order for a request to a protected route:

If an `Authorization` header is present it alone decides (no fallback to the cookie); otherwise the cookie decides. Implemented in `PrincipalResolver` (T-05).

1. `Authorization: Bearer ndk_<prefix>_<secret>` → agent (existing `authenticate`).
2. `Authorization: Bearer <admin token>` (constant-time compare) → `AdminToken` principal, honoured **only** on `/api/admin/*`.
3. Session cookie `newsdock_session` → `User` principal (sha256 of cookie → `sessions` join `users`; reject when `expires_at < now()` or `last_seen_at + idle < now()`).
4. None → anonymous.

**As built (T-05, 2026-10-27):** the resolver is called from FastAPI dependencies (`Guards.read`, `Guards.user`, and `Guards.write` registered app-wide) and caches the result on `request.state.principal`. It is not run in the outer `AuthMiddleware`: that middleware wraps CORS, so a 401 it produced would carry no `Access-Control-Allow-Origin` and the credentialed web UI could not read it. `AuthMiddleware` still enforces `/mcp` and `/api/subscriptions*` with its own `agent`/`key_id` state, so MCP and agent streams are untouched (NFR-3). A request carrying both a key and a cookie uses the key; a bad key does not fall back to the cookie. The write guard returns 403 `bad_origin` for a non-GET whose `Origin` is not in `cors_origins` and 415 when a body is present and its type is not `application/json`; GET and OPTIONS are never blocked by it. `logout` needs the cookie itself (401 without one, 204 for an already ended session).

Protection map:

| Path | Allowed principals | Anonymous when `auth_required=false` |
|---|---|---|
| `/mcp`, `/api/subscriptions*` | agent | anonymous agent (as today) |
| `GET /api/articles*` | user (any role), agent | allowed |
| `/api/live` | user | allowed (dev) |
| `/api/users*` | user role owner | still 401 (management is never open) |
| `/api/admin/*` | user role admin or owner, admin token | still 401 (management is never open) |
| `/api/auth/signup`, `/api/auth/login`, `/api/health` | public | public |
| `/api/auth/me`, `/api/auth/logout` | user | 401 |

Decision for the dev-mode row on `/api/admin/*` and `/api/users*`: they **always** require a principal; `auth_required=false` only relaxes reads and the live feed, because opening user and key management would defeat the roles.

Role order is `owner > admin > viewer`; the permission table is a dict `PERMISSIONS: dict[str, frozenset[Role]]` in `domain/accounts.py` (`read_articles`, `live_feed`, `manage_agents`, `manage_users`), used by a `require(permission)` dependency. Tests assert the table, not the routes (AC-9).

Rate limiting: agents keep the per-key fixed window. Humans are not rate-limited per request in this milestone, only on login failures and on opening live streams.

### Admin subscription delete (AC-12)
`DELETE /api/admin/subscriptions/{id}`: new `SubscriptionStore.delete_any(sub_id) -> bool` (SQL `DELETE … WHERE id = :id`), 204 or 404. Open agent streams already re-check `subscriptions.exists` on each keep-alive tick (push-delivery), so they end within `sse_keepalive_seconds`; a new stream request is 404 at once.

### Recovery route (C-17)
`POST /api/admin/users/reset-password` body `{email, password}`: **admin-token principal only** (an admin or owner *session* gets 403, so an admin cannot take over the owner account). Applies the password policy, replaces the hash, deletes every session of that user, returns 204; unknown email 404. `make user-reset-password EMAIL=<email>` reads the new password with `read -s` (not an argument, not in shell history), then posts it with curl exactly like `make agent-create` (needs `NEWSDOCK_ADMIN_TOKEN` in `.env`). If no admin token is configured the route does not exist (404), as the other admin routes.

## 3. Auth routes (C-13)

| Route | Body | Notes |
|---|---|---|
| `POST /api/auth/signup` | `{email, password}` | email regex + length ≤ 254; password length `min…128`; 403 `signup_closed`; 409 `email_taken` (race-safe via the unique index); 201 `{id,email,role}` |
| `POST /api/auth/login` | `{email, password}` | see algorithm; success sets cookie, returns user |
| `POST /api/auth/logout` | none | deletes the row, `Set-Cookie` with `Max-Age=0`; idempotent 204 |
| `GET /api/auth/me` | none | `{id,email,role}` |
| `GET /api/users` | none | `[{id,email,role,created_at}]` |
| `PATCH /api/users/{id}` | `{role}` | 409 `last_owner` if it would leave zero owners |
| `DELETE /api/users/{id}` | none | same last-owner rule; cascades sessions; an owner may delete themselves only if another owner exists |

Cookie attributes: `HttpOnly; SameSite=Lax; Path=/; Max-Age=<absolute>`; `Secure` when `auth_cookie_secure`. Signup does **not** log the user in (they log in next; keeps one path that sets cookies) **[assumption]**.

### Login algorithm
1. Normalize email. If the failure counter for it is at the limit → 429 `Retry-After: <seconds left in window>` before any hashing (AC-13).
2. Load user. Verify the password against the user's hash, or against a module-level dummy hash when absent (equal work, AC-5).
3. On failure: increment counter, 401 `{"error":"invalid_credentials"}` (same body for unknown email).
4. On success: clear counter, optionally rehash if `check_needs_rehash`, create session (`secrets.token_urlsafe(32)`, store sha256), delete this user's expired sessions, set cookie.

argon2-cffi `PasswordHasher()` defaults are used as is: argon2id v19, t=3, m=64 MiB, p=4, 16-byte salt, 32-byte hash. **[verified 2026-10-27, T-01, dev machine]** median 22.5 ms, p95 23.7 ms per hash; a wrong-password verify takes 23.6 ms median, so the 200 ms target holds with a wide margin and no tuning is proposed. Hashing runs in `run_in_threadpool`.

### First-owner and last-owner locks
```
BEGIN;
SELECT pg_advisory_xact_lock(7041001);          -- one constant for "users write"
-- signup:   role = 'owner' if not exists(select 1 from users) else 'viewer'
-- patch/delete: select count(*) from users where role='owner' (after lock)
COMMIT;
```
Advisory transaction locks are released at commit/rollback **[memory: Postgres docs]**. Because every write that depends on "how many owners" takes the lock, two concurrent first sign-ups serialize (AC-2) and two concurrent demotions cannot both succeed (AC-10).

## 4. Live feed (C-14)

`GET /api/live`:
1. Principal must be a user (any role) → else 401.
2. `StreamLimiter.try_acquire("user:<id>")` with `live_max_streams_per_user` (429 + `Retry-After`).
3. Start cursor: `Last-Event-ID` if valid (400 `invalid_last_event_id` otherwise), else `encode_cursor(max(seq))` read once at connect (new repo method `latest_seq()`); no backlog is sent. The history is the feed page's job.
4. Loop identical to `sse.py`: note `hub.generation()` → cursor query via `service.list_new(cursor, limit=200)` → emit `id: <cursor>\nevent: article\ndata: <json>` → wait on the hub with `sse_keepalive_seconds`; ping when idle; fallback poll every `sse_fallback_poll_seconds`.
5. Every keep-alive tick re-checks that the session is still valid (logout, expiry, deletion or demotion below viewer ends the stream). Latency bound = `sse_keepalive_seconds`.

**As built (T-09, 2026-10-27):** the loop lives in `adapters/streaming.py` (`article_events`, `Slot`, `frame`) and is used unchanged by the agent router and by `adapters/live.py`. The start cursor is `ArticleService.latest_cursor()` (`encode_cursor(max(seq))`, or position 0 on an empty table so the very first article is seen), read before the response starts. A caller that is an agent key gets 403, nobody 401; with `auth_required=false` the feed is open and not session-bound (one shared `anonymous` cap). The per-user cap is `live_max_streams_per_user` (3) on its own `StreamLimiter`. The keep-alive re-check calls `PrincipalResolver.session_alive`, which also refreshes `last_seen_at` at most once a minute: an open tab therefore keeps its session from idling out, but never past the absolute 7-day limit.

Optional ad-hoc filter (`theme`, `domain`, `text`) as query parameters, same SQL path as `list_new`; no new filter language **[assumption]**. The common loop in `sse.py` is factored into a helper used by both routers; the agent-specific parts (`_still_allowed`, stored cursor) are passed in. No behaviour change for agents (existing tests are the guard).

## 5. Web (C-15, C-16)

**API client** `src/lib/api/client.ts` wraps `fetch` with `credentials: "include"` and `Content-Type: application/json` for bodies; a 401 on any call except `/api/auth/*` redirects to `/login?next=<path>`; other errors surface as typed results. The live page uses `new EventSource(`${apiBaseUrl}/api/live`, {withCredentials: true})`; the browser resends `Last-Event-ID` itself. Types stay generated from `openapi.json` (`pnpm run generate:api`); new routes are added there.

**CORS (API, C-6)**: `CORSMiddleware(allow_origins=cors_origins_list, allow_credentials=True, allow_methods=[GET,POST,PATCH,DELETE], allow_headers=[Content-Type, Last-Event-ID])`. Credentialed responses need an explicit origin and the wildcard is not honoured for credentials **[memory: Fetch/CORS spec]**, which is why `allow_headers` is a list now. **[verified 2026-10-27, T-01]** Starlette answers a preflight from a listed origin with `Allow-Origin` = that origin, `Allow-Credentials: true`, methods `GET, POST, PATCH, DELETE` and headers including `Content-Type` and `Last-Event-ID`; an unlisted origin's preflight gets 400 and no `Allow-Origin`. Preflight tests assert these headers (T-07).

**Gate** `src/proxy.ts` (Next 16 name for middleware **[verified: docs/01-app/01-getting-started/16-proxy.md]**): matcher excludes `/login`, `/signup`, `_next/*`, `favicon.ico`; a missing `newsdock_session` cookie redirects to `/login?next=<path>`. The cookie is visible to the web server only because cookies are host-scoped, not port-scoped **[memory: RFC 6265]**, and the API host equals the page host (below). Docs say proxy is for optimistic checks only **[verified]**: every data call is authorized by the API, so a forged cookie shows an empty shell and gets 401s.

**Hostname alignment**: the root layout already reads runtime config and forces dynamic rendering (ADR-0014). It compares the request `Host` hostname with the hostname of `apiBaseUrl`; when both are loopback aliases (`localhost`, `127.0.0.1`) and differ, it `redirect()`s to the same path on the API's hostname. If neither is loopback and they differ, `/login` shows a configuration error naming both hosts (cross-site cookies would not work). Compose default stays `http://127.0.0.1:8000`.

**Pages**: `/login`, `/signup`, `/` (feed, existing), `/articles/[id]` (existing), `/live`, `/admin/agents`, `/admin/subscriptions`, `/admin/users`. Navigation reads `GET /api/auth/me` once (client context) and hides links the role cannot use; hiding is cosmetic, the API enforces. All text rendered via React text nodes (NFR-4). Key secrets live only in component state after creation, with a copy button, and are dropped on navigation (AC-11).

**Config**: no web setting changes (`api_base_url` still means what the browser calls). API gains the CORS and auth keys listed in design.md.

## 6. Failure table

| Failure | Detection | Response |
|---|---|---|
| Wrong/unknown credentials | verify fails | 401 uniform, counter++ |
| Too many failures | counter ≥ max in window | 429 `Retry-After` |
| Weak/long password | pydantic validator | 422 |
| Duplicate email | unique violation | 409 (no distinction in timing needed; sign-up reveals existence by design) |
| Sign-up closed | setting | 403 `signup_closed` |
| Two first sign-ups | advisory lock | one owner, one viewer |
| Demote/delete last owner | count after lock | 409 `last_owner` |
| Session expired/revoked | resolver | 401; UI → `/login?next=` |
| User deleted with open stream | keep-alive re-check | stream closes ≤ 15 s |
| Cookie tampered | sha256 lookup misses | 401 |
| DB error in resolver | `SQLAlchemyError` | 503 `unavailable` |
| Non-GET with foreign `Origin` | Origin check | 403 `bad_origin` |
| API unreachable from the browser | fetch throws | UI shows a retry notice, keeps the page |
| Page host differs from API host | layout check | redirect to the API's host (loopback) or configuration error |
| Non-JSON body on a write route | content-type check | 415 |
| Browser disconnects from SSE | ASGI disconnect | generator ends, slot released |

## 7. Security notes

- Passwords: argon2id only for humans; API keys keep sha256 (ADR-0016). Hashes never leave the repo layer; Pydantic response models exclude them (AC-1).
- Session ids: 256 bits, only the hash is stored, never logged. Logs carry user id and role, never email at INFO, never cookies or `Authorization`.
- Cookie flags above; `Secure` is a setting because local compose is plain HTTP.
- CSRF: `SameSite=Lax` plus JSON-only bodies (415 otherwise) plus an Origin check on every non-GET (403 `bad_origin` when `Origin` is present and not in `cors_origins`). Credentialed CORS is granted only to the listed origins. Other local apps on other ports are same-site, so Lax does not stop them; the Origin allowlist does.
- Open sign-up risk (spec risk 1): rate-limit on sign-up is **not** included; a flood creates viewer rows. Mitigation is `auth_signup_open: false`; a sign-up limiter is a backlog item if the user wants it **[assumption]**.
- Email addresses are personal data in the DB; no email is sent; no export tooling in scope.
- XSS: no `dangerouslySetInnerHTML`; agent names, emails and filter text are text nodes (existing lint/test pattern).
- Timing: dummy-hash verification on unknown email; uniform 401 body.

## 8. Test strategy hints (for /spec-plan)

- Domain unit tests (pure): permission table, password policy, limiter window, role transitions.
- API integration with real Postgres (existing `test-infra` api scene): signup/owner race with two threads, login/lockout, session expiry by editing `expires_at`/`last_seen_at`, route-by-role matrix, admin token vs session, live feed with an inserted row, logout ends a stream.
- Web unit (vitest): gate redirect, API client sends credentials and handles 401, host-alignment redirect, login form error states, nav by role, key shown once.
- CORS: preflight and actual-request header assertions in the API integration scene (allowed origin gets `Allow-Credentials: true`, unlisted origin gets none, `Last-Event-ID` allowed).
- Manual: AC-8, AC-11, AC-15 on the running stack.

## 9. Extension points (backlog)

Invites replace open sign-up by flipping `auth_signup_open` and adding an `invites` table; email reset needs a mailer port; MFA fits as a second step in the login route; `agents.owner_user_id` would add per-user agents; audit log is an append-only table written in the same transactions.
