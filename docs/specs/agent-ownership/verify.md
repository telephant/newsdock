# agent-ownership — Verify

Verified 2026-10-28 on branch `worktree-roadmap-ui-design` (commits `fc5d485`…`1dfde80` plus the doc-drift fixes below). **Verdict: pass with follow-ups.**

## What was run in this session

| Run | Result |
|---|---|
| `make check` (ruff lint and format, mypy strict, import-linter, layout, config, Python tests, web style/lint/format/types/tests, docs check) | exit 0; Python 470 passed (242 Docker tests deselected), web 163 passed |
| All Docker tests of `apps/api` and `packages/db` on a free Postgres port (`apps/api/tests/integration`, `packages/db/tests/integration`, including the model/migration drift test TC-34 and the listener tests) | 161 passed in 223 s |
| Mutation check (T-04): `scope_for` made to return the full scope | 9 ownership tests failed, then reverted |

The dev stack (up since before this work) held ports 5433 and 29092, so the Docker tests ran against their own Postgres: the new tests on port 55433 through the `side_db` fixture, the older ones through a temporary working-copy edit of `POSTGRES_PORT` in `.env.example` (restored; `git diff` is clean for it). The dev stack and its data were not touched.

## Results per acceptance criterion

| AC | Tests | Result | Evidence |
|---|---|---|---|
| AC-1 migration keeps data | TC-1 | pass | `test_agent_owner_migration.py::test_migration_keeps_legacy_agents_and_keys`: `demo-financial` and `push-live` get NULL owner, keys still authenticate; drift test `test_model_matches_migration` and `packages/db` TC-34 green |
| AC-2 creator recorded | TC-5, TC-8, TC-9 | pass | repo, in-memory route and HTTP tests; the admin token creates with NULL owner |
| AC-3 list by scope | TC-3, TC-5, TC-8, TC-10 | pass | A sees `a1`, B sees `b1`, owner role and token see all three |
| AC-4 foreign agent untouchable | TC-6, TC-8, `test_a_user_cannot_touch_…` | pass | issue key, revoke, disable, enable and subscription delete by another user all 404 and change nothing |
| AC-5 ownerless visibility | TC-3, TC-5, TC-6, TC-8, TC-10 | pass | admin and viewer 404 on `o1`; owner role and token disable and enable it |
| AC-6 running agents unaffected | TC-12 | pass | owned and ownerless keys pass `/mcp` and their own `/api/subscriptions` routes |
| AC-7 subscriptions follow agents | TC-7, TC-8, TC-9 | pass | list and delete follow the scope; foreign delete is 404 |
| AC-8 user delete orphans agents | TC-2, TC-11 | pass | `owner_id` becomes NULL; key and cursor and subscription rows survive; key still authenticates; owner list shows "no owner" |
| AC-9 every user manages own agents | TC-4, TC-9 | pass | a viewer runs create, key issue/revoke, subscription list/delete; anonymous 401, agent key 403 |
| AC-10 CLI and user management | TC-4, TC-13, TC-14 | pass (API half) | user routes owner-only; the `make agent-create` request makes an ownerless agent. See follow-up F-1 for the live run |
| AC-11 web shows returned rows | TC-15, TC-16 | pass | `Agents.test.tsx` (viewer: no creator; owner: "Created by", "no owner"), `Nav.test.tsx` (viewer sees both links), `roles.test.ts` |

All eleven ACs are `Verify: auto`; no manual checklist exists.

## Measurements

| What | Result |
|---|---|
| Queries per agents list (observation, no target) | two SELECTs regardless of agent count (agents LEFT JOIN users, then keys for the listed agents), by inspection of `SqlAgentsRepo.list_agents`; not measured at volume |

## Doc and code drift

Fixed in this run: the web shows the creator as a "Created by …" line on each agent card (the page uses cards), while `design.md` C-26, `design-detail.md` §6, spec AC-11 and TC-15 said "column" or "table"; all reworded. Fixed during implementation (recorded in `plan.md`): the migration downgrade is a no-op because DR-11 makes migrations forward-only (the first draft of AC-1 required a working downgrade); the `AgentRegistry` protocol change moved from T-02 to T-03; TC-14 now covers the API half automatically.

Checked and consistent: names in code and docs (`owner_id`, `owner_email`, `AgentScope`, `ALL`, `scope_for`, `agent_visible`, `add_key`, `list_visible`, `delete_visible`, migration `0007`); ADR-0023 Accepted and amendments in ADR-0016 and ADR-0020; CLAUDE.md, README, roadmap and the ui-login D-4 note updated; `list_all` and `delete_any` are gone.

Scope: nothing from `backlog.md` leaked in (no workspaces, transfer, role merge or path rename). Additions outside the spec are test infrastructure only: `apps/api/tests/integration/conftest.py` (side-port Postgres) and `adapters/agent_scope.py` (the one SQL predicate behind the design's `_visible`).

## Follow-ups (moved to `backlog.md`)

- **F-1 (P1, needs the developer):** smoke the change on the running dev stack: `make build APP=api` (and `APP=web`), `make migrate`, `make up`, then sign in as the first account and check that the Agents page lists `demo-financial` and `push-live` as "no owner" for the owner role and not for another user. The agent keeps working (its key is untouched). This changes the developer's own database (additive), so it was not run unasked.
- **F-2 (P2):** the `make test-infra` scenes (`db`, `kafka`, `sink`, `api`, `pipeline`, `e2e`, `stack`, `images`) were not run because they need ports 5433 and 29092, held by the dev stack; `test_stack.py` expects head `0007` and is unverified until then.
- **F-3 (P2):** open sign-up now lets any visitor create agents and keys (spec risk 2); the sign-up rate limit from the ui-login backlog matters more now.
- **F-4 (P2):** `admin` and `viewer` have identical permissions (spec D-7); merge them into one role.
- **F-5 (P3):** move the older Docker tests onto the `side_db` fixture so they run beside a dev stack, as the new ones do.
- **F-6 (P3):** rename `/api/admin/*` to something that fits routes ordinary users call (kept on purpose, ADR-0023).
