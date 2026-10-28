# agent-ownership — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation

Run 2026-10-28 with grep over `tests.md`, `tasks/` and the ADR:

| Check | Result |
|---|---|
| AC → test (all 11 ACs have ≥ 1 TC) | pass (AC-1:1, AC-2:2, AC-3:4, AC-4:2, AC-5:5, AC-6:1, AC-7:2, AC-8:2, AC-9:2, AC-10:3, AC-11:2) |
| AC → design (design.md coverage table lists AC-1…AC-11) | pass |
| AC → task (each AC in ≥ 1 task's `Implements`) | pass |
| Orphan tests (every TC-1…TC-16 named by exactly one task) | pass |
| Names consistent (`owner_id`, `owner_email`, `AgentScope`, `scope_for`, `0007`, `/api/admin/*`) | pass |
| No doc treats a Proposed ADR as decided | pass (ADR-0023 Accepted 2026-10-28; no "Proposed" text left) |
| Backlog leakage (workspaces, transfer, role merge, sign-up limiter, path rename) | none in tasks |
| Open questions / unchecked checklist items | none |

Findings: none open. One note carried into T-05: the exact command that exports the OpenAPI JSON is not documented in the repo (only `generate:api` is), so T-05 exports it from `create_app().openapi()`.

## Order and reasons

**Spike first (T-01).** The one claim not yet checked against a real database is that an additive nullable `owner_id` with `ON DELETE SET NULL` migrates the existing `demo-financial` and `push-live` rows untouched and leaves their keys, cursors and subscriptions working. Every later task builds on that column, and the API integration tests need the `0007` head, so it goes first.

| Task | Title | Implements | Depends on |
|---|---|---|---|
| T-01 | Migration 0007, model column, FK behaviour (spike) | AC-1, AC-8 (DB level) | none |
| T-02 | Domain: `AgentScope`, `scope_for`, permission table, summary fields | AC-3, AC-5, AC-9, AC-10 | T-01 |
| T-03 | Repos: scope on agents and subscriptions | AC-2, AC-3, AC-4, AC-5, AC-7 | T-01, T-02 |
| T-04 | Routes and guard, API integration tests | AC-2…AC-10 | T-03 |
| T-05 | Web: roles, Agents creator column, regenerated types | AC-11 | T-04 |
| T-06 | Docs, CLI check, full checks | AC-10 (CLI), docs | T-05 |

## Milestones

- **Skeleton (T-01 + T-02 + T-03):** the data model and the scope exist and are proven in Postgres. AC-1, AC-2, AC-3, AC-4, AC-5, AC-7 pass at repo level.
- **Behaviour (T-04):** every route honours the scope. AC-6, AC-8, AC-9, AC-10 pass over HTTP.
- **Done (T-05 + T-06):** web and docs match. AC-11 passes; `make check` and the affected `make test-infra` scenes are green.

Rough effort: T-01 small, T-02 small, T-03 medium, T-04 medium, T-05 small, T-06 small.

## Definition of done (every task)

1. Tests listed in the task are written first, seen failing, then green.
2. `make test APP=<app>` for the touched app is green; `make check` is green at T-06 (and for `api`/`web` before each commit where feasible).
3. Docs that repeat a changed fact are updated in the same change (CLAUDE.md rule); stale files are noted.
4. No secrets, no hand-edited generated client (`apps/web/src/lib/api/` is regenerated).
5. One commit per task: `agent-ownership T-NN: <title>`.

## Out of scope (stays in the backlog)

Workspaces, transfer and sharing of agents, adopting orphans through a dedicated UI action, `OWNER=` on `make agent-create`, merging the `admin` and `viewer` roles, sign-up rate limit, renaming `/api/admin/*`.
