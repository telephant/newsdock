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
