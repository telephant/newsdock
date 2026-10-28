# signup-rate-limit — Verify

Verified 2026-10-28 on branch `worktree-roadmap-ui-design` (commits `80f8ed0`…`063cbd9` plus the doc fixes below). **Verdict: pass with follow-ups.**

## What was run in this session

| Run | Result |
|---|---|
| `make check` (ruff lint and format, mypy strict, import-linter, layout, config, Python tests, web style/lint/format/types/tests, docs check) | exit 0; Python 499 passed (252 Docker tests deselected), web 166 passed |
| All Docker tests of `apps/api` and `packages/db` on a free Postgres port (includes the model/migration drift test, the new sign-up limit tests and the ownership tests) | 171 passed in 200 s |
| Earlier in the work: the suite found 11 failures in `test_live_api.py` (one host signing up many users hit the new default); fixed by switching sign-up limits off in that file's two test servers | green afterwards |

The dev stack held ports 5433 and 29092, so the older Docker tests ran through a temporary working-copy edit of `POSTGRES_PORT` in `.env.example` (restored; clean in `git status`) and the newer ones on the `side_db` fixture (port 55433). The dev stack and its data were not touched.

## Results per acceptance criterion

| AC | Tests | Result | Evidence |
|---|---|---|---|
| AC-1 one address limited | TC-1, TC-5, TC-9 | pass | unit limiter; route test: 201 ×3 then 429 `too_many_signups`, integer `Retry-After`, 3 user rows, hash counter shows refused requests never hashed |
| AC-2 other addresses unaffected | TC-2, TC-8, TC-10 | pass | unit; spike proves `TestClient(app, client=…)` sets `request.client.host`; route test |
| AC-3 global cap | TC-3, TC-5, TC-11 | pass | five addresses, four 201 then 429 with `Retry-After` |
| AC-4 window recovers | TC-4, TC-12 | pass | fake clock past the window → 201 and the count restarts |
| AC-5 invalid/closed requests free | TC-6, TC-13 | pass | five 422s then a valid 201; ten 403s with the closed flag leave the limiter empty (`tracked() == 0`) |
| AC-6 duplicates count | TC-14 | pass | 409, 409, then 429 |
| AC-7 first account is the owner | TC-15 | pass | default limits, first sign-up 201 with role `owner` |
| AC-8 zero switches off | TC-6, TC-16 | pass | 50 sign-ups all 201; limiter holds no state |
| AC-9 bounded memory | TC-7 | pass | table never exceeds its cap; newest address still limited; 60 parallel threads cannot overshoot a budget of 10 |
| AC-10 sign-up form explains a 429 | TC-20 | pass | `SignupForm.test.tsx`: "try again in about 2 minutes", and "later" without a wait; stays on the form |
| AC-11 quota stops the next agent | TC-17 | pass | unit with a disabled agent counted; real `count_owned` counts all statuses against Postgres |
| AC-12 owner role and token exempt | TC-18 | pass | 3 creations each at a quota of 2, all 201 |
| AC-13 quota is per user | TC-19 | pass | user B creates while A is at the quota |
| AC-14 Agents page explains the quota | TC-21 | pass | `Agents.test.tsx`: "reached the agent limit" |
| AC-15 settings consistent | TC-22 | pass | `Settings` defaults 5 / 50 / 60 / 10, `signup_window_seconds` 3600; `make config-python` green inside `make check` |

All fifteen ACs are `Verify: auto`; no manual checklist exists.

## Measurements

| What | Result |
|---|---|
| Peer address a host browser presents through Docker Desktop **[verified]** | `docker logs newsdock-api-1` on the dev stack: 1030 GETs and 7 POSTs from `172.19.0.1` (the `newsdock_agent` network gateway, i.e. the host), 27171 POSTs from `172.19.0.4` (the demo agent container), 2200 GETs from `127.0.0.1` (health checks). Every browser on the machine is one address |
| Is 5 per address per hour enough? | Not for one machine creating many accounts: locally the per-address limit is in effect the total (see F-1). Fine for normal use; the defaults are provisional |

## Doc and code drift

Fixed in this run: the README said the *total* cap protects local use, but because all local browsers share one address the per-address limit binds first; reworded and pointed at `auth_signup_max_per_address`. Fixed during implementation (recorded in `plan.md`): the existing live-feed tests needed the sign-up limits switched off; the README no longer calls a sign-up "read-only" (a viewer can create agents since agent-ownership).

Checked and consistent: names in code and docs (`SignupLimiter.attempt`, `tracked`, `UNKNOWN_ADDRESS`, `too_many_signups`, `too_many_agents`, `agent_quota_reached`, `count_owned`, `signup_window_seconds`, the four settings and their YAML rows); the web messages match design-detail §5; no ADR was needed or written (none referenced).

Scope: nothing from `backlog.md` leaked in (no trusted-proxy handling, persistence, CAPTCHA, invites or agent deletion). The only change outside the spec's file list is the `test_live_api.py` settings.

## Follow-ups (moved to `backlog.md`)

- **F-1 (P1, needs the developer):** smoke the change on the running dev stack: rebuild `api` and `web`, `make up`, then try to sign up more than five accounts from the browser; expect the sixth to show the "Too many sign-ups" message with a wait, and note whether 5 per hour is too tight for your own use (raise `auth_signup_max_per_address` in `infra/config/newsdock.yaml` if so). Not run unasked because it needs the rebuilt images.
- **F-2 (P2):** `make test-infra` scenes were not run (ports 5433 and 29092 held by the dev stack).
- **F-3 (P2):** trusted-proxy setting so a deployment behind a reverse proxy sees real client addresses (already in this spec's backlog).
- **F-4 (P2):** deleting an agent; until then the quota is a hard stop (already in the backlog).
