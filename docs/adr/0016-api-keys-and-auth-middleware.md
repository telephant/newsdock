# ADR-0016: Admin-issued API keys, hashed, verified by one ASGI middleware

Status: **Accepted 2026-10-14** (user accepted at /spec-design agent-platform; an unset admin token disables admin routes (404); anonymous traffic shares one rate bucket)

## Context
M2 needs agent identity on MCP (spec D-2, D-5). Today there is no auth. The MCP app is mounted inside FastAPI (ADR-0003), so FastAPI dependencies do not cover `/mcp`. Humans get accounts only in the later `ui-login` spec.

## Options
**Key storage:** (a) plaintext; (b) **sha256 of a 256-bit random secret + a short public prefix for lookup**; (c) argon2/bcrypt (needed for low-entropy passwords, wasteful per request for random keys).
**Where to check:** (a) per-tool decorator; (b) **one pure-ASGI middleware on the outer app for paths under `/mcp`**, which puts the verified agent on `scope["state"]`; tools read it from the request.
**Registry access:** (a) self-service; (b) **admin routes guarded by `NEWSDOCK_ADMIN_TOKEN` (env, secret)**, replaced by account roles in `ui-login`.

## Decision (proposed)
Key format `ndk_<prefix>_<secret>`; store `prefix` (unique) and `sha256(secret)`; compare with `hmac.compare_digest`; plaintext shown once. Middleware returns 401 before any tool runs, 429 on rate limit. `auth_required=false` maps every request without a valid key to the anonymous agent. Public `GET /api/*` stays open (spec D-7). Admin routes live under `/api/admin/*` with their own token check; unset token disables them.

## Consequences
One enforcement point, easy to test; fast hash is safe only because keys are high-entropy random (never use this scheme for user passwords: `ui-login` will use argon2). No key rotation overlap yet (backlog). A leaked admin token is full registry control.
