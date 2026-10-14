# agent-platform — Design detail

Reference only; not required reading for approval.

## 1. Admin routes (`/api/admin`, `Authorization: Bearer <admin token>`)

| Method, path | Body | Result |
|---|---|---|
| POST `/agents` | `{name}` (`[a-z0-9_-]{1,40}`) | 201 `{agent_id, name, key_id, api_key}`; 409 if name exists |
| GET `/agents` | | `[{agent_id, name, status, keys:[{key_id, prefix, created_at, revoked_at, last_used_at}]}]` |
| POST `/agents/{id}/keys` | | 201 `{key_id, api_key}` |
| DELETE `/agents/{id}/keys/{key_id}` | | 204, sets `revoked_at` |
| POST `/agents/{id}/disable` / `/enable` | | 204 |

Admin check: constant-time compare to `NEWSDOCK_ADMIN_TOKEN`; unset → 404. An agent key on these routes → 403 (it is a valid bearer but not the admin token), no token → 401.

## 2. Key handling (domain, pure)

`make_key()` → `ndk_<prefix>_<secret>` with `prefix = token_urlsafe(6)`, `secret = token_urlsafe(32)`. `parse_key(raw)` splits on `_` (prefix/secret contain no `_`: use hex or base32 alphabets to guarantee; decided in implementation). `hash_secret = sha256(secret).hexdigest()`. Verify: lookup by `prefix` (unique index), `hmac.compare_digest(hash)`, key not revoked, agent active. `last_used_at` updated at most once per minute per key.

## 3. Middleware algorithm (C-11)

1. Path not under `/mcp` → pass through.
2. Resolve the key if a header is present (below). With `auth_required=false`, a request without a *valid* key becomes the anonymous agent (id None, name `anonymous`; one shared rate bucket, key `anonymous`); a valid key still wins, so the demo agent keeps its identity and cursor.
3. Read `Authorization: Bearer`; verify (above); failure → 401 JSON `{"error":"unauthorized"}` with `WWW-Authenticate: Bearer`.
4. `limiter.allow(agent_id, now)`; deny → 429 + `Retry-After: <seconds to window end>`.
5. `scope["state"]["agent"] = Agent(id, name)`; call app.

Order matters: auth before limit so unauthenticated floods cannot fill limiter memory (limiter keyed only by verified agent ids or the single anonymous bucket).

## 4. Cursor semantics (ADR-0017)

- `list_new_articles(cursor?, limit?)`: explicit cursor → as M1. No cursor and authenticated → stored `seq` if any, else first-run window. Returns `next_cursor` as M1.
- `ack_cursor(cursor)`: decode → `seq`; `INSERT ... ON CONFLICT (agent_id) DO UPDATE SET seq = GREATEST(agent_cursors.seq, EXCLUDED.seq)`. Anonymous → ToolError `anonymous_agent`. Bad cursor → ToolError `invalid_cursor`.
- Retention may delete articles older than the cursor; harmless (`seq > cursor`).

## 5. Demo agent change

`McpApiClient` builds the MCP client with a header `Authorization: Bearer ${api_key}` (transport detail verified by the T-01 spike; the current `Client(url)` form takes no headers). `FileCursorStore` and `cursor_file` setting removed; `AgentLoop` calls `list_new_articles(None, limit)` then `ack_cursor(next_cursor)` after all submits succeed. Missing key setting → a startup warning; on HTTP 401 the agent logs a clear message and keeps retrying (the 401 is detected with one probe request because the mcp client hides the status, see plan T-07). The `agent_state` volume is dropped from compose (no other state).

## 6. Migration 0004

Creates the three tables; no data migration. Hand-written against `newsdock_db.models`; autogenerate no-op test must stay green.

## 7. Security notes

Keys/admin token never logged (log `prefix` only); config loader already rejects secret-looking keys in YAML; error messages do not distinguish unknown vs. revoked; CORS `allow_methods` stays GET (admin routes are not browser-called). No TLS (local compose). Open reads (D-7) are a documented gap until `ui-login`.

## 8. Full failure table

| Case | Handling |
|---|---|
| Duplicate agent name | 409 |
| Malformed `Authorization` | 401 |
| DB down during auth | 503, tool not run |
| `ack_cursor` older than stored | no-op, returns stored cursor |
| Two agents same machine, same key | allowed; they share a cursor (documented) |
| Key issued, never shown (lost) | issue a new key, revoke the old |
