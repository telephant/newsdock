# signup-rate-limit — Tests

Spec: [spec.md](spec.md) §6 · Design: [design.md](design.md). Every AC has at least one test; every test names its AC.

## Test data and fixtures

- No GDELT data. Sign-up bodies use generated emails (`u1@x.io`, …) and a fixed valid password; peer addresses are fake IPv4 strings.
- Unit tests drive `SignupLimiter` with a fake clock (a list the test advances), in `apps/api/tests/unit/`.
- Route tests are Docker integration tests on the `side_db` fixture (`apps/api/tests/integration/conftest.py`), with `create_app(Settings(...), signup_limiter=SignupLimiter(..., clock=fake))` and `TestClient(app, client=("10.0.0.7", 50000))` to set the peer address.
- Quota unit tests reuse the scope-honouring fakes of `tests/unit/test_admin_scope.py`; the real-count test runs against Postgres.
- Web tests use the existing vitest + testing-library setup with stubbed `fetch`.

## Test cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | unit | Given max 3 per address, When one address makes 4 attempts, Then the first three are allowed and the fourth is refused with a wait ≥ 1 s |
| TC-2 | AC-2 | unit | Given address A is exhausted, When address B attempts, Then B is allowed |
| TC-3 | AC-3 | unit | Given max total 4 and per address 10, When five addresses attempt once each, Then four are allowed and the fifth is refused |
| TC-4 | AC-4 | unit | Given a limit reached, When the fake clock passes the window, Then the next attempt is allowed and the count restarts at 1 |
| TC-5 | AC-1, AC-3 | unit | A refused attempt records nothing (a global refusal leaves the address count unchanged and the reverse); the refused wait is the larger remaining time of the refusing windows; the window is not extended by refused attempts |
| TC-6 | AC-8, AC-5 | unit | With both maxima 0 every attempt is allowed and `tracked()` stays 0; with only one maximum 0 the other still applies |
| TC-7 | AC-9 | unit | Given a small table cap, When more distinct addresses attempt than the cap, Then `tracked()` never exceeds the cap and the newest address is still limited correctly |
| TC-8 | AC-2 | unit | Spike: a tiny route echoing `request.client.host` sees the address given to `TestClient(app, client=(host, port))`, and a missing client maps to the shared "unknown" key |
| TC-9 | AC-1 | integration | Route: per-address max 3, four valid sign-ups from one address: 201 ×3, then 429 `too_many_signups` with an integer `Retry-After` ≥ 1 and no fourth user row |
| TC-10 | AC-2 | integration | Route: after address A is exhausted, address B signs up: 201 |
| TC-11 | AC-3 | integration | Route: total max 4, per address 10, five addresses: 201 ×4 then 429 with `Retry-After` |
| TC-12 | AC-4 | integration | Route: after the limit is reached the injected clock moves past the window and the same address gets 201 |
| TC-13 | AC-5 | integration | Route: max 2; five invalid sign-ups (bad email, short password) return 422 and a valid one still returns 201; with `auth_signup_open=False` ten requests return 403 and the injected limiter's `tracked()` is 0 |
| TC-14 | AC-6 | integration | Route: max 2, existing a@x.io; two sign-ups with a@x.io return 409 and a third with a new email returns 429 |
| TC-15 | AC-7 | integration | Route: empty users table and default limits; the first sign-up returns 201 with role `owner` |
| TC-16 | AC-8 | integration | Route: both maxima 0; 50 valid sign-ups from one address all return 201 |
| TC-17 | AC-11 | unit + integration | `agent_quota_reached` truth table (0 = off); unit routes with fakes: a viewer with two agents (one disabled) and `agents_max_per_user=2` gets 409 `too_many_agents` on the third and nothing is created; integration: `count_owned` counts all statuses against Postgres |
| TC-18 | AC-12 | unit | `agents_max_per_user=2`: an owner-role user and the admin token each create three agents (201 ×6) |
| TC-19 | AC-13 | unit | User A at the quota; user B creates an agent: 201 |
| TC-20 | AC-10 | unit (web) | `signupMessage` for a 429 with `retryAfter` 120 says to try again in about 2 minutes, without a wait says "later"; `SignupForm` shows it and stays on the page |
| TC-21 | AC-14 | unit (web) | `agentActionMessage` maps 409 `too_many_agents` to the limit sentence; `Agents` shows it after the create form is submitted |
| TC-22 | AC-15 | unit + check | `Settings()` defaults equal 5 / 50 / 60 / 10 and `signup_window_seconds` is 3600; `make config-python` passes with the four rows in `infra/config/newsdock.yaml` |

## AC coverage (checked by grep at plan time)

| AC | Tests |
|---|---|
| AC-1 | TC-1, TC-5, TC-9 |
| AC-2 | TC-2, TC-8, TC-10 |
| AC-3 | TC-3, TC-5, TC-11 |
| AC-4 | TC-4, TC-12 |
| AC-5 | TC-6, TC-13 |
| AC-6 | TC-14 |
| AC-7 | TC-15 |
| AC-8 | TC-6, TC-16 |
| AC-9 | TC-7 |
| AC-10 | TC-20 |
| AC-11 | TC-17 |
| AC-12 | TC-18 |
| AC-13 | TC-19 |
| AC-14 | TC-21 |
| AC-15 | TC-22 |

All 15 ACs are `Verify: auto`; there is no manual checklist.

## Measurements

| What | How |
|---|---|
| Peer address a host browser presents to the API through Docker Desktop | `docker logs` of the API after one browser sign-up; already observed as the gateway `172.19.0.1` during design, recorded again at verify |
| Whether 5 per address per hour is enough for a normal household | judgement at verify from the above; the defaults are provisional, not pass/fail |
