# agent-ownership — Design

Spec: [spec.md](spec.md) · Detail (reference only): [design-detail.md](design-detail.md) · Diagrams: [diagrams/index.html](diagrams/index.html) · Decision: [ADR-0023](../../adr/0023-agent-ownership-by-scope-filter.md) (Accepted 2026-10-28)

**Reading order:** this file → the diagrams (each has a "Check" box) → the checklist at the bottom. Component ids start at C-20 to stay clear of the ui-login ids (C-10…C-17).

## What changes, in one paragraph

An `agents.owner_id` column records the creating user. One pure function, `scope_for(principal)`, turns the caller into a **scope**: *everything* (owner role, admin token) or *only agents whose `owner_id` is me* (any other user). The agent and subscription repos take that scope and apply it inside every query, so a route cannot forget to filter. Foreign and ownerless agents look absent to non-owners (404). Every signed-in role may use the agent routes. Agent keys, MCP and the agent-facing routes are not touched.

## Components

| Id | Job | Notes |
|---|---|---|
| C-20 | `AgentScope` + `scope_for(principal)` | Pure, in `domain/agents.py`. Token and `owner` role → all; other user → own. Agent principals never reach it |
| C-21 | Agents repo with scope | `create_agent(name, key, owner_id)`; `list/get/add_key/revoke_key/set_status` take a scope; summary gains `owner_id`, `owner_email` |
| C-22 | Subscriptions repo with scope | `list_visible(scope)`, `delete_visible(sub_id, scope)`; the agent-facing `*_own` methods stay |
| C-23 | Admin routes | Read the principal, build the scope once, pass it down; 404 when the repo says "not visible" |
| C-24 | Permission table and guard | `manage_agents` held by all roles; the guard accepts any user session or the admin token |
| C-25 | Migration 0007 and model | `agents.owner_id` nullable FK to `users.id`, `ON DELETE SET NULL`, indexed; additive |
| C-26 | Web | `canManageAgents` true for any role; each agent card shows its creator for the owner role; types regenerated from OpenAPI |

## Flows

- **F-20 create:** session user → `scope_for` → `create_agent(..., owner_id=user_id)`; the token creates with `owner_id=NULL` (diagram 2).
- **F-21 list:** `list_agents(scope)` and `list_visible(scope)` return only the visible rows (diagram 2).
- **F-22 act on one agent** (issue key, revoke, disable, enable, delete subscription): the repo applies the scope in the same statement; zero rows → 404 (diagram 2).
- **F-23 user deleted:** Postgres sets `owner_id` to NULL; keys, cursors and subscriptions are untouched; the owner role now sees the agent as "no owner" (diagram 3).
- Agent-facing paths (`/mcp`, `/api/subscriptions*`) keep the existing key resolver and never call the scope.

## Contracts

| Where | Change |
|---|---|
| `agents` table | `+ owner_id uuid NULL → users.id ON DELETE SET NULL`, index `ix_agents_owner_id` |
| `AgentSummary` (REST) | `+ owner_id: str \| null`, `+ owner_email: str \| null` |
| `AdminSubscription` (REST) | unchanged (already has `agent_name`) |
| Routes under `/api/admin` | same paths and verbs; a foreign or unknown id is 404, a non-JSON write is 415 as before |
| Permission `manage_agents` | `{owner, admin, viewer}` |

Route names stay under `/api/admin/*` (renaming them would churn the generated client and the CLI for no behaviour change; backlog if wanted).

## The tricky parts

- **Authorization by construction:** the scope is a required argument of every repo method that reads or writes agents or subscriptions, so "forgot the filter" is a type error, not a test gap. A meta-test still walks the router and fails if an agent route is not in the isolation test (AC-4).
- **No existence leak by id:** "not yours", "no owner" and "does not exist" are all 404 for non-owners. Creating a taken name is 409 for everyone (spec D-8, accepted).
- **Owner sees ownerless:** the owner scope applies no filter, so orphaned and legacy agents appear with `owner_email: null`.
- **Identity of the caller is re-read per request:** the role comes from the database through the session resolver (ui-login), so demoting a user takes effect at once.
- **Races:** two creates with one name are settled by the existing unique index; a delete of a user during an agent create settles by the FK (the insert fails or the owner is nulled) and is handled as a normal 409/404.

## Top failure modes

| Failure | Effect | Handling |
|---|---|---|
| A new agent route skips the scope | cross-user leak | scope is a required repo argument; router-walking test |
| Owner role cached in the web | stale links | the API decides; links are only hints |
| Migration on a large `agents` table | none expected | additive nullable column, tiny table |
| Admin token leaked | sees all agents | unchanged risk (ADR-0016); token is CLI-only |

## Technology

No new library or service. SQLAlchemy 2 + Alembic (ADR-0008), FastAPI dependencies (existing guards), OpenAPI-generated web types (existing). One new ADR: [ADR-0023](../../adr/0023-agent-ownership-by-scope-filter.md).

## AC coverage

| AC | Component / flow |
|---|---|
| AC-1 migration keeps data | C-25 |
| AC-2 creator recorded | C-20, C-21, C-23 · F-20 |
| AC-3 list by scope | C-20, C-21, C-23 · F-21 |
| AC-4 foreign agent untouchable | C-21, C-23 · F-22 |
| AC-5 ownerless visibility | C-20, C-21 · F-21, F-22 |
| AC-6 running agents unaffected | agent-facing paths unchanged (no component) · C-25 additive |
| AC-7 subscriptions follow agents | C-22, C-23 · F-21, F-22 |
| AC-8 deleted user orphans agents | C-25 FK · F-23 |
| AC-9 every user manages own agents | C-24, C-26 · F-20 |
| AC-10 CLI and user management | C-23 (token path), existing user routes |
| AC-11 web shows returned rows | C-26 |

## Questions to answer before approving this design

- [x] Is a repo-level required `scope` argument the right place to enforce ownership (versus a route-level check or Postgres row-level security, ADR-0023)?
- [x] Should a taken agent name stay a 409 for everyone, even though it reveals that the name exists?
- [x] Should the owner role see the creator's email on the Agents table (a user-identifying column visible only to the owner)?
- [x] Is keeping the `/api/admin/*` paths acceptable now that ordinary users call them?
- [x] When an owner-role user creates an agent, should it be owned by them (as designed), or be ownerless like CLI agents?
