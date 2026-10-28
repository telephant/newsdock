# signup-rate-limit — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation

Run 2026-10-28 with grep over `tests.md`, `tasks/`, `design.md`:

| Check | Result |
|---|---|
| AC → test (all 15 ACs have ≥ 1 TC) | pass (AC-1:3, AC-2:3, AC-3:3, AC-4:2, AC-5:2, AC-6:1, AC-7:1, AC-8:2, AC-9:1, AC-10…AC-15: 1 each) |
| AC → design (design.md coverage table lists AC-1…AC-15) | pass |
| AC → task (each AC in ≥ 1 task's `Implements`) | pass |
| Orphan tests (TC-1…TC-22 each named by exactly one task) | pass |
| Names consistent (`SignupLimiter`, `attempt`, `too_many_signups`, `too_many_agents`, `auth_signup_max_per_address`, `auth_signup_max_total`, `auth_signup_window_minutes`, `agents_max_per_user`, `count_owned`) | pass |
| No doc treats a Proposed ADR as decided | pass (no ADR; design.md explains why) |
| Backlog leakage (trusted proxy, persistence, CAPTCHA, invites, deleting agents) | none in tasks |
| Open questions / unchecked checklist items | none (design checklist answered on the recommended options at the user's instruction to finish the feature) |

Findings: none open. Note for T-02: the existing Docker sign-up tests may sign up more than 5 users from the test client's one address; if so they get `Settings(auth_signup_max_per_address=0)` or a raised limit, noted in the commit message.

## Order and reasons

**Spike first (T-01).** The one claim the later route tests depend on and nobody has checked is that the peer address can be set per test client (`TestClient(app, client=(host, port))`) and read as `request.client.host`. T-01 opens with that spike (TC-8), then builds the pure limiter and the settings, which carry most of the logic and need no database.

| Task | Title | Implements | Depends on |
|---|---|---|---|
| T-01 | Peer-address spike, `SignupLimiter`, settings and config rows | AC-1, AC-2, AC-3, AC-4, AC-8, AC-9, AC-15 | none |
| T-02 | Sign-up route uses the limiter (429, ordering, wiring) | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8 | T-01 |
| T-03 | Per-user agent quota | AC-11, AC-12, AC-13 | T-01 |
| T-04 | Web messages for the 429 and the agent limit | AC-10, AC-14 | T-02, T-03 |
| T-05 | Docs and final checks | all (docs), AC-15 | T-04 |

## Progress

- T-01 ✅ 2026-10-28 — spike TC-8: `TestClient(app, client=(host, port))` reaches `request.client.host`, so the route tests can give each client its own address. `domain/signuplimit.py` (`SignupLimiter`: two fixed windows, atomic under a lock, refusals record nothing and never extend a window, `Retry-After` is the larger remaining time, bounded table, 0 = off per limit) with TC-1…TC-7 plus a 60-thread overshoot test; settings `auth_signup_max_per_address=5`, `auth_signup_max_total=50`, `auth_signup_window_minutes=60`, `agents_max_per_user=10`, `signup_window_seconds`, and the four rows in `infra/config/newsdock.yaml` (TC-22). `make check-python`: 488 passed (mypy strict, import-linter, config check green). Note: ruff also formats the Python code blocks in the spec markdown, so new design docs must keep them formatted.

## Milestones

- **Skeleton (T-01 + T-02):** a flood of sign-ups from one address is refused with a 429 on a real database. AC-1…AC-9, AC-15.
- **Quota (T-03):** AC-11…AC-13.
- **Done (T-04 + T-05):** the web explains both refusals; docs and `make check` match. AC-10, AC-14.

Rough effort: T-01 small, T-02 small–medium, T-03 small, T-04 small, T-05 small.

## Definition of done (every task)

1. Tests listed in the task are written first, seen failing, then green.
2. `make check-python` (and `make check-web` for T-04) is green; Docker tests for the touched files pass on the `side_db` fixture.
3. Docs that repeat a changed fact are updated in the same change; no secrets; generated web types are regenerated, never hand-edited.
4. One commit per task: `signup-rate-limit T-NN: <title>`.
5. New numbers are settings (`make config-python`), never literals in code.

## Out of scope (stays in the backlog)

Trusted-proxy handling, persistent or multi-worker counters, CAPTCHA, invites, email verification, deleting agents, other quotas.
