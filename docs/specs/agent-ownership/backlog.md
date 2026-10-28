# agent-ownership — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Smoke the change on the dev stack (P1, from verify F-1):** rebuild the `api` and `web` images, `make migrate`, `make up`, sign in and check that `demo-financial` and `push-live` show as "no owner" for the owner role only.
- **Run the `make test-infra` scenes (P2, from verify F-2):** `db`, `api`, `stack` and the rest need ports 5433 and 29092 free; `test_stack.py` expects head `0007`.
- **Older Docker tests onto the `side_db` fixture (P3, from verify F-5):** so they run beside a dev stack.
- **Rename `/api/admin/*` (P3, verify F-6):** ordinary users call these routes now; kept on purpose (ADR-0023) to avoid churn.
- **Workspaces / projects (P2):** agents, keys and subscriptions belong to a workspace; users are members with a role per workspace. The real multi-tenant model; per-user ownership is the cheap step before it.
- **Simplify roles (P2):** after this spec `admin` and `viewer` have identical permissions (D-7); fold them into one `user` role, and keep `owner` as the see-all role.
- **Sign-up rate limit (P2, from the ui-login backlog):** more relevant now that a sign-up can create agents and keys (risk 2).
- **Transfer an agent to another user (P3):** needed when someone leaves; deleting a user orphans their agents (D-5).
- **Adopt an ownerless agent from the UI (P3):** today only the `owner` role and the admin token can manage orphans, and nobody can give one an owner (D-4).
- **`OWNER=<email>` on `make agent-create` (P3):** CLI agents are ownerless by default (D-3).
- **Share an agent with another user (P3):** read-only or manage access to one agent.
- **Per-user agent quota (P3).**
- **Audit log of who created/revoked what (P3, from the ui-login backlog).**
