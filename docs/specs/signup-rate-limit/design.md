# signup-rate-limit — Design

Spec: [spec.md](spec.md) · Detail (reference only): [design-detail.md](design-detail.md) · Diagrams: [diagrams/index.html](diagrams/index.html)

**Reading order:** this file → the diagrams (each has a "Check" box) → the checklist at the bottom. Component ids start at C-30 to stay clear of ui-login (C-10…C-17) and agent-ownership (C-20…C-26). **No new ADR:** the design reuses the in-memory, single-worker limiter pattern that ADR-0016 and ADR-0020 already accepted, and nothing here is hard to reverse (a setting, a class, one route check).

## What changes, in one paragraph

A pure `SignupLimiter` counts sign-up attempts in two fixed windows, one per client address and one global. `POST /api/auth/signup` asks it after the closed-check and input validation and before the argon2 hash; a refusal is a 429 with `Retry-After` and costs no hash and no database write. Separately, `POST /api/admin/agents` refuses a non-owner user who already owns `agents_max_per_user` agents with 409 `too_many_agents`. Four new settings carry every number. The web maps the two refusals to plain messages.

## Components

| Id | Job | Notes |
|---|---|---|
| C-30 | `SignupLimiter` (`domain/signuplimit.py`) | Pure, injectable clock, thread-safe (`attempt(address) -> Decision`), two fixed windows, bounded table, 0 = off per limit |
| C-31 | Sign-up route (`adapters/accounts_api.py`, wiring in `adapters/http.py`) | Order: closed → validate → limiter → hash → insert; address = socket peer; 429 `too_many_signups` with `Retry-After` |
| C-32 | Agent quota (`domain/agents.py`, `adapters/agents_repo.py`, `adapters/admin.py`) | `count_owned(owner_id)`, `agent_quota_reached(count, max)`; applies exactly when the caller's scope is "own" (`not scope.everything`); 409 `too_many_agents` |
| C-33 | Settings (`config.py`, `infra/config/newsdock.yaml`) | `auth_signup_max_per_address`, `auth_signup_max_total`, `auth_signup_window_minutes`, `agents_max_per_user`; `signup_window_seconds` property |
| C-34 | Web messages (`features/auth/messages.ts`, `features/admin/messages.ts`) | Sign-up 429 uses `formatWait(retryAfter)`; agent 409 `too_many_agents` gets its own sentence |

## Flows

- **F-30 sign-up attempt:** closed? → 403; invalid? → 422; `limiter.attempt(address)` over? → 429; else hash, insert (201 or 409). Only the last two outcomes count (diagram 2).
- **F-31 create agent:** guard → scope; if the scope is "own" and the user owns ≥ max agents → 409 `too_many_agents`; else create as before (diagram 1).
- **F-32 window lifecycle:** a window starts at the first counted attempt, blocks once the count reaches the max, and ends by time alone (diagram 3).

## Contracts

| Where | Change |
|---|---|
| `POST /api/auth/signup` | new 429 `{"detail": "too_many_signups"}` + `Retry-After: <seconds>`; other statuses unchanged |
| `POST /api/admin/agents` | new 409 `{"detail": "too_many_agents"}` (distinct from 409 `name_taken`) |
| Settings (api section) | `auth_signup_max_per_address: 5`, `auth_signup_max_total: 50`, `auth_signup_window_minutes: 60`, `agents_max_per_user: 10`; 0 = off |
| REST schema | no model change; OpenAPI regenerates only if route responses are declared (not needed) |
| Database | none |

## The tricky parts

- **A refused attempt must not count.** `attempt` checks both windows first and records in both only when both allow, so a global refusal does not burn one address's budget and the reverse.
- **Retry-After tells the truth.** It is the larger remaining time of the window(s) that refused, so waiting that long can succeed.
- **Atomic check-and-record.** Sync FastAPI routes run in a thread pool, so `attempt` holds one lock; the login limiter's check/record split is fine for failures but a sign-up budget must not be overshot by parallel requests.
- **Bounded memory.** Expired windows are pruned lazily and a hard cap evicts the oldest address (same as `LoginLimiter`). An attacker cycling more than the cap of addresses can flush counts; accepted at this scale.
- **Docker address collapse (verified):** the API log shows host browsers arrive as the Docker gateway `172.19.0.1` and sibling containers as `172.19.0.4`, so locally the per-address limit is effectively a second global limit. The global cap and the generous defaults are the answer; a trusted-proxy setting is backlog.
- **Quota race:** two simultaneous creates by one user can both pass the count and overshoot by the number of requests in flight; the quota is a soft cap, accepted (spec D-7 does not promise a hard one).
- **Exemption by scope, not by role name:** the quota applies when `scope_for(principal)` is "own", so the owner role and the token stay exempt without a second role check.

## Top failure modes

| Failure | Effect | Handling |
|---|---|---|
| API restarts | counters reset | accepted (single worker, in memory) |
| Flood fills the global cap | real sign-ups wait for the window | `Retry-After` tells them; `auth_signup_open: false` is the hard brake |
| Peer address missing | request is counted under one "unknown" key | never skipped, so no bypass |
| Database down on `count_owned` | 503 via the existing handler | no partial create |
| Setting is 0 | that limit is off | AC-8 |

## Technology

No new library. Python stdlib (`threading.Lock`, `time.monotonic`), existing `Decision` from `domain/ratelimit.py`, existing FastAPI route style, existing web message helpers. No ADR.

## AC coverage

| AC | Component / flow |
|---|---|
| AC-1 per-address limit | C-30, C-31 · F-30 |
| AC-2 other addresses unaffected | C-30 · F-30 |
| AC-3 global cap | C-30 · F-30 |
| AC-4 window recovers | C-30 · F-32 |
| AC-5 invalid/closed requests free | C-31 order · F-30 |
| AC-6 duplicates count | C-31 · F-30 |
| AC-7 first account still owner | C-31 (path unchanged) |
| AC-8 zero switches off | C-30, C-33 |
| AC-9 bounded memory | C-30 |
| AC-10 sign-up 429 message | C-34 |
| AC-11 quota stops the next agent | C-32 · F-31 |
| AC-12 owner role and token exempt | C-32 · F-31 |
| AC-13 quota is per user | C-32 · F-31 |
| AC-14 agent quota message | C-34 |
| AC-15 settings consistent | C-33 |

## Questions to answer before approving this design

- [x] Is a fixed window acceptable, given it allows up to twice the limit across a window boundary (a sliding window costs more memory and code)?
- [x] Should a refused attempt stay uncounted (so an attacker cannot extend their own block by retrying)?
- [x] Is it right to ignore `X-Forwarded-For` for now, accepting that behind a proxy all callers share one address?
- [x] Is a soft quota (can overshoot by in-flight requests) acceptable for `agents_max_per_user`?
- [x] Should the quota count disabled agents (hoarding stays capped) even though agents cannot be deleted yet?

Answered 2026-10-28 on the recommended options (yes to all five), because the user asked to finish the feature through the /spec-* stages without stopping at each review; change any of them before /spec-plan or later through an update of this design.
