# agent-ownership — Design detail

Reference only; not required reading for approval. Overview: [design.md](design.md).

## 1. Schema (C-25, migration `0007_agent_owner`)

```
agents.owner_id  uuid  NULL  REFERENCES users(id) ON DELETE SET NULL   -- fk_agents_owner_id_users
index ix_agents_owner_id (owner_id)
```

- Existing rows stay NULL. Forward-only (DR-11): the downgrade is a documented no-op, like 0006.
- Model: `Agent.owner_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)`.
- `packages/db/tests/integration/test_schema.py` gets the new column and FK; `test_stack.py` expected head becomes `0007`.

## 2. Scope (C-20, `domain/agents.py`, pure)

```python
class AgentScope(BaseModel):  # frozen
    everything: bool
    owner_id: str | None = None  # set when everything is False


ALL = AgentScope(everything=True)


def scope_for(principal: UserPrincipal | AdminTokenPrincipal) -> AgentScope:
    if isinstance(principal, AdminTokenPrincipal) or principal.role is Role.OWNER:
        return ALL
    return AgentScope(everything=False, owner_id=principal.user_id)
```

An explicit `everything` flag avoids the trap of `owner_id=None` meaning both "all" and "ownerless". The domain imports `Role`/principals from `domain/accounts.py`, which already imports `Agent` from `domain/agents.py`; to avoid a cycle `scope_for` lives in `domain/accounts.py` and `AgentScope` in `domain/agents.py`.

## 3. Repos

**Agents repo (C-21).** One private helper builds the predicate:

```python
def _visible(scope: AgentScope):
    return true() if scope.everything else AgentRow.owner_id == scope.owner_id
```

| Method | Behaviour |
|---|---|
| `create_agent(name, key, owner_id: str \| None)` | inserts with `owner_id` |
| `list_agents(scope)` | `agents LEFT JOIN users` where `_visible`, keys for those agents only; summary has `owner_id`, `owner_email` |
| `agent_visible(agent_id, scope) -> bool` | `exists(select 1 from agents where id and _visible)`; used by `issue_key` |
| `add_key(agent_id, key, scope) -> str \| None` | inserts only if visible, in one session; `None` → route answers 404 |
| `revoke_key(agent_id, key_id, scope)` | `UPDATE api_keys … WHERE agent_id IN (select id from agents where id=:a and _visible)` |
| `set_status(agent_id, status, scope)` | `UPDATE agents … WHERE id=:a AND _visible` |

`find_key`, `key_usable`, `touch_key`, `get_cursor`, `advance_cursor` (agent-facing) are unchanged and take no scope.

**Subscriptions repo (C-22).** `list_visible(scope)` joins `subscriptions → agents` with `_visible`; `delete_visible(sub_id, scope)` deletes where the subscription's `agent_id IN (select id from agents where _visible)`. `list_all` and `delete_any` are removed once no caller remains (the token and owner use `ALL`). `create`, `list_own`, `get_own`, `delete_own`, `count_own`, `exists` stay for agents.

Protocols `AgentRegistry` and `SubscriptionStore` change accordingly; the fakes in the unit tests change with them.

## 4. Routes (C-23, `adapters/admin.py`)

`build_admin_router` keeps its signature plus the `Principal` dependency result:

```python
principal = Depends(require_admin)  # already returns the principal
scope = scope_for(principal)  # token or user; agents cannot pass the guard
```

| Route | Change |
|---|---|
| `POST /agents` | `owner_id = principal.user_id` for a user, `None` for the token |
| `GET /agents` | `registry.list_agents(scope)` |
| `POST /agents/{id}/keys` | `registry.add_key(id, key, scope)`; `None` → 404 |
| `DELETE /agents/{id}/keys/{kid}` | scoped revoke; false → 404 |
| `POST /agents/{id}/disable\|enable` | scoped `set_status`; false → 404 |
| `GET /subscriptions` | `subscriptions.list_visible(scope)` |
| `DELETE /subscriptions/{id}` | `delete_visible(id, scope)`; false → 404 |

Unknown id, foreign id and ownerless id (for non-owners) all take the same 404 branch. Because the FastAPI guard resolves the principal once per request (cached in `request.state`), the scope costs no extra database round-trip.

## 5. Guard and permission (C-24)

- `PERMISSIONS["manage_agents"] = frozenset({Role.OWNER, Role.ADMIN, Role.VIEWER})`; `can()` is unchanged.
- `Guards.admin` is unchanged in code (token, or a user for whom `can(role, "manage_agents")`); the comment is updated, because the name no longer means "admin role". Renaming the guard is out of scope.
- An agent key presenting on these routes still gets 403, anonymous 401.

## 6. Web (C-26)

- `features/auth/roles.ts`: `canManageAgents(role) → role !== null`; `asRole` is unchanged.
- Nav and the `/admin/agents`, `/admin/subscriptions` page guards already call `canManageAgents`, so viewers get the links with no other change.
- `Agents.tsx`: when `useSession().role === "owner"`, add a "Created by <email | no owner>" line to each agent card (the page lists agents as cards, not a table); the empty-state title becomes "You have no agents yet." for everyone.
- `pnpm --dir apps/web run` generator refreshes `src/lib/api/openapi.json` and `types.ts` from the API; the check that generated types are current already exists in `check-web`.
- All text is rendered as escaped React text (unchanged rule); the email is shown only to the owner role, and the API already limits the field to what the scope may see.

## 7. Failure table

| Case | Result |
|---|---|
| Viewer lists agents | 200, only own rows (empty at first) |
| Viewer disables another user's agent | 404, nothing changed |
| Viewer disables an ownerless agent | 404 |
| Owner disables an ownerless agent | 204 |
| Admin token creates an agent | 201, `owner_id` NULL |
| Name taken (any owner) | 409 `name_taken` |
| Owner deletes user A | A's agents get `owner_id` NULL; keys keep working |
| Agent key calls `/api/admin/agents` | 403 |
| No credential | 401 |
| Database unavailable | 503 (existing handling in the principal guard) |

## 8. Security notes

- Isolation is enforced in SQL predicates that take the scope as a required argument; the web only mirrors it.
- Foreign ids return 404, not 403, so ids cannot be probed. Name probing through 409 is accepted (spec D-8).
- Open sign-up now grants key creation (spec risk 2); the existing per-agent rate limit and the `auth_signup_open` flag are the brakes, the sign-up rate limit stays in the backlog.
- The owner sees user emails on the Agents page; users never see another user's email through agents.
- No secret, key hash or password hash is added to any response.

## 9. Test seams (for /spec-plan)

- Unit: `scope_for` for token, owner, admin, viewer; routes with fake registry and store, including a test that walks `router.routes` and asserts each agent or subscription route appears in the isolation matrix.
- Integration (Postgres): repo scope behaviour, FK `SET NULL` on user delete, migration up/down on a database holding `demo-financial`-like rows.
- Infra: `make agent-create` still creates an ownerless agent; `test_stack` head `0007`.
- Web: `Agents.test.tsx` and `Subscriptions.test.tsx` with a viewer session; nav test for a viewer.
