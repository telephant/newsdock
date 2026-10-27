# ui-login — Verification

Date: 2026-10-27 · Spec: [spec.md](spec.md) · Tests: [tests.md](tests.md) · Plan: [plan.md](plan.md) · Verdict: **pass with follow-ups**

## Run summary (this session, after the last code change)

| Check | Result |
|---|---|
| `make check` (ruff, ruff format, mypy strict on 195 files, import-linter 4 contracts kept, layout, config, web lint, format, typecheck, docs) | **exit 0**: Python 449 passed (207 Docker-marked tests deselected), web 107 passed in 15 files |
| `make test-rules` | **exit 0**, 23 passed |
| `make test-infra` (every scene: db, kafka, sink, api, pipeline, e2e, stack, images) | first full run: **183 passed, 1 failed** in 6 min. The failure was a **regression caused by this feature**: `test_stack.py` TC-26 hard-coded the migration head `"0005"`, and migration `0006` moved it. Fixed to `"0006"`; `SCENE=stack` re-run: 9 passed. Every other scene was green in the full run, including e2e agent isolation (AC-13 of the MVP), images, kafka, sink, db and the whole API scene (agent paths unchanged) |
| Manual runs M-1, M-2, M-3 | **31 of 31 checks passed** in a real Chrome against real `postgres`, `migrate`, `api` and `web` containers built from this branch (T-14, isolated compose project; the developer's volume and images untouched) |

## Acceptance criteria

| AC | TC (tests run in this session) | Result | Evidence |
|---|---|---|---|
| AC-1 sign-up creates a viewer | TC-1, TC-2, TC-3, TC-4 | pass | `test_accounts_api.py` (12 Docker): viewer role, `$argon2id$` hash, no hash field in the response, no secret in logs; `test_passwords.py` (6); schema checks in `test_users_repo.py` (13) |
| AC-2 first account is the owner | TC-5 | pass | `test_users_repo.py`: 8 concurrent first sign-ups, 20 rounds, exactly one owner each; with the advisory lock disabled the race tests fail (mutation check, T-03) |
| AC-3 bad sign-up rejected | TC-6, TC-7 | pass | `test_accounts.py` (unit), `test_accounts_api.py`: 409, 422 (short, long, bad email), 403 when closed, row count unchanged |
| AC-4 login sets a session | TC-8, TC-9, TC-10 | pass | `test_accounts_api.py` (cookie flags `HttpOnly; SameSite=Lax; Path=/; Max-Age=604800`, `Secure` by setting, only the sha256 stored), `test_session_api.py` (`/me`, 415, `bad_origin`), `test_cors.py` (23 cases); real browser: cookie sent on `fetch` and `EventSource` (T-01, M-1) |
| AC-5 wrong credentials do not leak | TC-11, TC-12 | pass | identical 401 bodies, no session row; **M-b measured** (below) |
| AC-6 logout and expiry end the session | TC-13, TC-14, TC-15 | pass | `test_accounts.py`, `test_session_api.py` (logout, idle, absolute, refresh at most once a minute) |
| AC-7 reads need a session or a key | TC-16, TC-17 | pass | `test_session_api.py` matrix (anonymous 401, session 200, key 200, revoked 401, forged cookie 401, health open, dev mode open, 401 carries CORS headers); the whole existing agent suites passed unchanged |
| AC-8 the UI gates its pages | TC-18, TC-19, TC-20, TC-21, **TC-22 manual** | **manual-ok** | `gate.test.ts` 7, `hosts.test.ts` 7, `proxy-handler.test.ts` 8, `client/api.test.ts` 8, `LoginForm.test.tsx` 9, `SignupForm.test.tsx` 7; M-1: `localhost` redirected to `127.0.0.1/login?next=/`, login shows the feed, cookie-less visitor redirected |
| AC-9 roles enforced on the server | TC-23, TC-24, TC-25 | pass | `test_accounts.py` (permission table), `test_roles_api.py` (13: viewer, admin, owner on agent and user routes; agent key 403; anonymous 401, also with `auth_required=false`), `Nav.test.tsx` 10 |
| AC-10 owner manages roles safely | TC-26, TC-27 | pass | `test_roles_api.py` (promote, last-owner 409 on demote and delete, HTTP race of two owners), `Users.test.tsx` 8; M-2.0 in the real UI |
| AC-11 agents and keys from the UI | TC-28, **TC-29 manual** | **manual-ok** | `Agents.test.tsx` 9 (shown once, dropped on dismiss and unmount, never in the list); M-2: key shown once, gone after reload, `/mcp` 200 then 401 after the confirmed revoke |
| AC-12 subscriptions screen | TC-30, TC-31 | pass | `test_roles_api.py` (list, delete, 404, viewer 403, stream 404), `Subscriptions.test.tsx` 7; M-2.4 in the real UI |
| AC-13 login attempts limited | TC-32, TC-33, TC-34 | pass | `test_loginlimit.py` (10), `test_accounts_api.py` (lockout with `Retry-After`, other accounts unaffected, window expiry), `test_config.py` (defaults equal the yaml rows) |
| AC-14 admin token still works for the CLI | TC-35 | pass | `test_roles_api.py::test_admin_token_matrix` and `test_session_api.py` token half; sessions work without a token; token opens neither `/api/users` nor logout |
| AC-15 live feed | TC-36, TC-37, TC-38, **TC-39 manual** | **manual-ok** | `test_live_api.py` (15, real uvicorn: no backlog, resume by `Last-Event-ID`, filter, cap, logout and user delete end the stream), `test_stream_api.py` unchanged (11), `Live.test.tsx` 11; M-3: new row on the page in 113 ms, no reload, anonymous 401, logout elsewhere ended it in 18 s |
| AC-16 owner recovery by CLI | TC-40, TC-41 | pass | `test_reset_password.py` (8: token 204, sessions 403, 404 without a token, lockout lifted, no secret in logs), `test_user_reset_password.py` (9: password never in argv or output) |

13 ACs pass by automated tests, 3 (AC-8, AC-11, AC-15) are `manual-ok`; none failing. TC-42 (the T-01 spike) passed on 2026-10-27 (details in plan.md).

## Measurements (provisional targets, not pass/fail)

| Id | Measured | Result |
|---|---|---|
| M-a argon2 time | defaults (argon2id v19, t=3, m=64 MiB, p=4): hash median 22.5 ms, p95 23.7 ms (T-01); a failed login through the real app 23.9 ms median, 25.7 ms p95 (this run) | far below the 200 ms target; no tuning proposed |
| M-b unknown vs wrong-password timing | 200 requests each through the real app and hasher: unknown email 23.78 ms median, wrong password 23.93 ms median, gap -0.15 ms (-0.6 %) | no systematic gap (dummy-hash verification works) |
| M-c insert → live event | 20 samples through NOTIFY: median 13 ms, max 19 ms (T-09); one insert reached a real browser page in 113 ms | well under the 15 s keep-alive |
| M-d defaults (12 h idle, 7 d absolute, 5 failures per 15 min, min password 10) | not measurable | confirmed by the user at design, kept as settings |

## Doc drift

Fixed in this stage:

1. `design.md` Settings line lacked `auth_cookie_name` and the two web keys (`session_cookie`, `login_required`) that T-10 added; added.
2. ADR-0014 listed only three web settings; amended (dated 2026-10-27) with the two new keys.
3. `design-detail.md` §1 used planned index names (`users_email_key`, `sessions_user_idx`, `sessions_expires_idx`); now the real ones (`uq_users_email`, `ck_users_role`, `ix_sessions_user_id`, `ix_sessions_expires_at`). §3 said login deletes "this user's expired sessions" (it deletes all expired ones); and the recovery paragraph said the script posts "exactly like `make agent-create`" (it uses stdin and a header file); both corrected.
4. `spec.md` §3 still stated the old CORS defaults as a current fact; marked as the state before this spec.
5. `plan.md` T-11 listed the wrong per-file web test counts (SignupForm is 7, not 8; the 26 total was right).
6. `infra/scripts/tests/test_stack.py` hard-coded alembic head `0005` (the real regression above).

Checked and accurate: the design's route table equals the generated OpenAPI paths (only the path parameter names differ); every setting named in the design is a real field; ADR-0016 (amended), ADR-0020 and ADR-0021 match the code; the README and `CLAUDE.md` describe the behaviour that the M-1 to M-3 runs exercised.

Deviations from the original design, all recorded where they happened and none changing an AC: resolver as FastAPI dependencies rather than in `AuthMiddleware` (so 401s keep CORS headers); host alignment in `src/proxy.ts`, not the root layout (the layout cannot see the path; `NextURL` rewrites `127.0.0.1`); two web settings `session_cookie` and `login_required`; settings named `auth_min_pw_length` and `cors_allow_cookies` (the config loader rejects keys containing "password" or "credential"); `DELETE /api/admin/subscriptions/{id}` added at planning (AC-12 needed it); ADR-0016 amended (no 404 for admin routes when no token is set); reset-password also clears the login throttle; ADR-0021 chose credentialed CORS over the proposed proxy.

## Scope

Nothing from `backlog.md` leaked into the code (no webhook, invite, MFA, OAuth, audit, email flows; checked by search of `apps/api/src` and `apps/web/src`). Beyond the spec's wording, and documented: the two web settings, the throttle reset on password reset, the agent export script sending its key (reads need auth now), the `ArticleItem` extraction (no behaviour change), the shared stream loop `adapters/streaming.py` (agent behaviour unchanged, proven by its suite).

## Follow-ups (moved to backlog.md)

1. Open sign-up has no limiter (spec risk 1, the user's choice): rate-limit it (P2).
2. Chrome only: repeat the cross-port cookie, `EventSource` and manual checklists in Safari and Firefox (P3).
3. The live page keeps its session from idling out through the keep-alive check; decide whether it should not (P3).
4. The login throttle is per process; move it to Postgres before running several API workers (P3).
5. The new screens are unstyled HTML (P3).
6. `test_stack.py` hard-codes the alembic head; read it from the migration scripts so the next migration cannot break it (P3, found here).
7. The full 8-service `make up` with real GDELT ingestion and the demo agent was not run by hand; the `stack`, `e2e` and `images` scenes cover its wiring and passed (P3).

## Verdict

**Pass with follow-ups.** All 16 acceptance criteria are covered and green in this session (13 automated, 3 manual with evidence), the full Docker suite passes after fixing the one regression this feature caused, the documentation drift found was fixed, and no backlog scope leaked in. `gates.verify: approved`, `stage: done`. Next milestone candidates from the backlogs: the remaining M2 delivery items (webhook and MCP-notification channels, the demo agent consuming the stream, a sign-up rate limit; all P2), then M3 (semantic search, Events and Mentions, article bodies).
