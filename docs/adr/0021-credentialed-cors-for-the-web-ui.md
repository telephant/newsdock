# ADR-0021: The browser keeps calling the API directly, with credentialed CORS

Status: **Accepted 2026-10-27** (user chose credentialed CORS over a same-origin proxy at /spec-design ui-login)

## Context
A login cookie must reach the API from the browser. Today the browser calls the API at `web.api_base_url` (default `http://127.0.0.1:8000`) and CORS allows only `GET` without credentials. Cookies are scoped by host, not port, so a page and an API on the same hostname share the cookie and count as same-site (`SameSite=Lax` is sent), while `localhost` vs `127.0.0.1` are different hosts. ADR-0014 had deferred the alternative, a web-server proxy.

## Options
1. **Credentialed CORS**: explicit origins, `allow_credentials=True`, methods `GET,POST,PATCH,DELETE`, headers `Content-Type, Last-Event-ID`; `fetch(..., {credentials: "include"})`, `EventSource` with `withCredentials`.
2. Same-origin Next.js route-handler proxy at `/api/*` (streams SSE; first-party cookie; extra hop; amends ADR-0014). Proposed first, not chosen.
3. `next.config` rewrites: build-time target, conflicts with ADR-0014's runtime config.

## Decision
Option 1. Hostname alignment is enforced by the web server: the root layout redirects to the API's hostname when the page host differs and both are loopback aliases. The API requires `Content-Type: application/json` on writes (415 otherwise) and rejects a non-GET with an `Origin` that is not in `cors_origins` (403 `bad_origin`). ADR-0014 is not changed: `web.api_base_url` still means what the browser calls.

## Consequences
+ No extra hop, no SSE pass-through to build, no change to the web network design or ADR-0014. − Page and API must share a hostname (handled by the redirect; a deployment on two registrable domains would need a shared parent domain or the proxy option). − CSRF protection rests on the Origin allowlist and JSON-only bodies, because other local apps on other ports are same-site. − CORS settings now matter for security and are covered by integration tests.
