# ADR-0020: The API owns accounts; sessions are opaque ids in Postgres; roles are a column

Status: **Accepted 2026-10-27** (user reviewed the alternatives: Auth.js, stateless cookie, role tables and another hash; kept this bundle at /spec-design ui-login)

## Context
`ui-login` adds human accounts with roles (spec D-1, D-4) next to agent API keys (ADR-0016). Passwords must use a slow hash (ADR-0016 already reserves argon2 for them). The article routes, the admin routes and the live feed live in the API, and agents have no browser. Next.js 16 documents both stateless (signed cookie) and database sessions and says its `proxy.ts` is for optimistic checks only.

## Options
**Where identity lives:** (a) **the API (Postgres tables, FastAPI routes)**; (b) Next.js (an auth library such as Auth.js, own session store), with the API trusting a token from it.
**Session format:** (a) **opaque random id, sha256 stored in `sessions`**; (b) signed/JWT stateless cookie.
**Roles:** (a) **text column with CHECK, fixed permission table in code**; (b) roles/permissions tables.
**Password hash:** (a) **argon2id via `argon2-cffi`**; (b) bcrypt/scrypt.

## Decision (proposed)
All (a). The API is the only place that decides who someone is and what they may do, for browsers, agents and the CLI alike (one enforcement point, as ADR-0016/0019). Sessions are server-side so logout, deletion and demotion take effect at once and open live streams can be closed on the next keep-alive. Three fixed roles map to four permissions in a dict in `domain/accounts.py`. `argon2-cffi` 25.1.0 is current (PyPI, checked 2026-10-27).

## Consequences
+ Logout and revocation are immediate; no key rotation or JWT blocklist. + Agent and human auth share the middleware and the same tests. + Nothing to sync between two services. − One DB read per authenticated request (small indexed join; acceptable at this scale). − The API grows an account surface (signup, throttle, lock rules) that an auth library would otherwise supply. − Login throttling is in memory, valid for one API worker (same limit as the agent limiter). − Per-user agents, invites, email flows and MFA are later additions, not free.

## Amendment 2026-10-28 (agent-ownership, ADR-0023)
Per-user agents arrived: `manage_agents` now means "manage the agents you may see" and is held by `owner`, `admin` and `viewer` alike (so `admin` and `viewer` have the same permissions), while `manage_users` stays with `owner`. The `owner` role additionally sees every agent through the unfiltered scope. The permission dict in `domain/accounts.py` is still the one place roles are decided.
