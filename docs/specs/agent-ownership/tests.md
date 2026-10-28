# agent-ownership — Tests

Spec: [spec.md](spec.md) §6 · Design: [design.md](design.md). Every AC has at least one test; every test names its AC.

## Test data and fixtures

- No GDELT data is involved. Users, agents, keys and subscriptions are built in each test through the repos or the HTTP routes.
- Roles under test: `owner`, `admin`, `viewer` (users A, B per role as needed), the admin token, an agent key (owned agent `a1`, ownerless `o1`).
- Integration tests use the same Docker Postgres pattern as `apps/api/tests/integration/test_roles_api.py` (compose project per file, `pytestmark = pytest.mark.docker`). A legacy-shape database for TC-1 is built by migrating to `0006`, inserting `demo-financial` and `push-live` rows with keys, then upgrading to `0007`.
- Unit tests use fakes that honour the scope (in-memory registry and subscription store) in `apps/api/tests/unit/`.

## Test cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | integration | Given a DB at `0006` with `demo-financial`, `push-live` and their keys, When `0007` runs, Then `agents.owner_id` exists and is NULL for both, both keys still authenticate (`find_key`) |
| TC-2 | AC-8 | integration | Given an agent with a key, a cursor and a subscription owned by user A, When A's user row is deleted, Then the agent's `owner_id` is NULL and the key, cursor and subscription rows remain |
| TC-3 | AC-3, AC-5 | unit | `scope_for`: admin token → everything; `owner` role → everything; `admin` and `viewer` → only their `user_id`; the scope object is frozen |
| TC-4 | AC-9, AC-10 | unit | Permission table: `manage_agents` held by owner, admin, viewer; `manage_users` by owner only; `can()` unknown permission still raises |
| TC-5 | AC-2, AC-3, AC-5 | integration | Repo: `create_agent(owner_id=A)` stores the owner; `list_agents(scope)` returns A's own only for A's scope, everything incl. ownerless with `owner_email` for the full scope; ownerless rows never appear in an own-scope list |
| TC-6 | AC-4, AC-5 | integration | Repo: with B's scope, `add_key`, `revoke_key`, `set_status` on A's agent and on an ownerless agent return "not visible" and change nothing; with A's scope and the full scope they succeed |
| TC-7 | AC-7 | integration | Repo: `list_visible` and `delete_visible` follow the scope (A sees only a1's subscription, B's delete of it affects 0 rows, the full scope sees and deletes both) |
| TC-8 | AC-2, AC-3, AC-4, AC-5, AC-7 | unit | Admin routes with scope-honouring fakes: the isolation matrix over every `/api/admin` agent and subscription route for viewer A, viewer B, owner, token (list, create, issue key, revoke, disable, enable, subscription list/delete); foreign and unknown ids both 404; a **router-walking meta-test** fails if any `/api/admin` route containing `agents` or `subscriptions` is missing from the matrix; the token creates with `owner_id` None, a session with its user id |
| TC-9 | AC-9 | integration | Given a freshly signed-up `viewer`, When it creates an agent, lists, issues and revokes a key, creates (as that agent) and lists/deletes a subscription through the admin routes, Then all succeed and touch only that agent; with no credential the same routes give 401; an agent key gets 403 |
| TC-10 | AC-3, AC-5 | integration | HTTP, real DB: users A and B (viewer/admin), the owner and the token; A's list = a1, B's = b1, owner's and token's = a1, b1, o1 (with `owner_email`); admin and viewer cannot see or disable `o1` (404), the owner can disable and re-enable it |
| TC-11 | AC-8 | integration | HTTP, real DB: the owner deletes user A; `a1`'s key still reaches `/mcp`; `a1` is absent from B's list and present in the owner's list with `owner_email` null |
| TC-12 | AC-6 | integration | Agent keys of owned `a1` and ownerless `o1` call `/mcp` (`list_new_articles`, `ack_cursor`) and their own `/api/subscriptions` routes exactly as before; subscription and cursor rows are unchanged by the migration |
| TC-13 | AC-10 | integration | User routes (`GET /api/users`, role change, delete): owner 200; admin and viewer 403; agent key 403; none 401 |
| TC-14 | AC-10 | integration + unit | The request `make agent-create` sends (`POST /api/admin/agents` with the admin token and a JSON name) returns the key once and the agent's `owner_id` is NULL, and the owner role can list it (`test_agent_ownership_api.py`); the shell wrappers are unchanged and keep their tests (`infra/scripts/tests/test_user_reset_password.py`, `test_make_test.py`); `test_stack.py` expects head `0007`. **Revised at T-06:** a live `make up` run is not part of the automated test, because it needs a rebuilt API image and a migration of the developer's own database; it is a manual step in `/spec-verify` |
| TC-15 | AC-11 | unit (web) | `Agents.test.tsx`: given the API returns one agent, a viewer session renders that row only and the empty-state sentence "You have no agents yet." when none; an owner session additionally renders a "Creator" column with the email or "no owner" |
| TC-16 | AC-11 | unit (web) | `Subscriptions.test.tsx` renders only returned rows; `Nav.test.tsx`: a viewer sees the Agents and Subscriptions links (and no Users link); `roles.test`: `canManageAgents` true for every known role, false for null/unknown |

## AC coverage (checked by grep at plan time)

| AC | Tests |
|---|---|
| AC-1 | TC-1 |
| AC-2 | TC-5, TC-8 |
| AC-3 | TC-3, TC-5, TC-8, TC-10 |
| AC-4 | TC-6, TC-8 |
| AC-5 | TC-3, TC-5, TC-6, TC-8, TC-10 |
| AC-6 | TC-12 |
| AC-7 | TC-7, TC-8 |
| AC-8 | TC-2, TC-11 |
| AC-9 | TC-4, TC-9 |
| AC-10 | TC-4, TC-13, TC-14 |
| AC-11 | TC-15, TC-16 |

All 11 ACs are `Verify: auto`; there is no manual checklist.

## Measurements

None. The spec sets no numeric target. One observation is recorded at verify time, not as pass/fail: the query count of the agents list for a user with many agents (expected: constant, one agents query and one keys query).
