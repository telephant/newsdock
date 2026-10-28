# agent-ownership — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Workspaces / projects (P2):** agents, keys and subscriptions belong to a workspace; users are members with a role per workspace. The real multi-tenant model; per-user ownership is the cheap step before it.
- **Simplify roles (P2):** after this spec `admin` and `viewer` have identical permissions (D-7); fold them into one `user` role, and keep `owner` as the see-all role.
- **Sign-up rate limit (P2, from the ui-login backlog):** more relevant now that a sign-up can create agents and keys (risk 2).
- **Transfer an agent to another user (P3):** needed when someone leaves; deleting a user orphans their agents (D-5).
- **Adopt an ownerless agent from the UI (P3):** today only the admin token can manage orphans (D-3).
- **`OWNER=<email>` on `make agent-create` (P3):** CLI agents are ownerless by default (D-3).
- **Share an agent with another user (P3):** read-only or manage access to one agent.
- **Per-user agent quota (P3).**
- **Audit log of who created/revoked what (P3, from the ui-login backlog).**
