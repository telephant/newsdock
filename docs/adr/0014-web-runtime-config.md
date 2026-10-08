# ADR-0014: Web settings are read at runtime, not inlined at build time

Status: **Accepted 2026-10-06** (user accepted the recommended defaults at /spec-design externalize-config)

## Context
`NEXT_PUBLIC_API_BASE` is inlined into the client bundle at build time. The web Dockerfile and compose never set it, so every image carries the default and cannot be re-pointed without a rebuild. The web settings (API base, poll interval, page size) must come from the same YAML/env as the Python services (spec D-3, D-6).

## Options
1. **Server-side runtime read**: the root layout calls `await connection()` (forcing dynamic rendering), reads env then the YAML `web` section, and passes the values to client components through a context provider. Per Next.js docs, server components read `process.env` at request time under dynamic rendering, and `NEXT_PUBLIC_*` is frozen at build. **[verified: Next docs 2026-10-06; confirmed by the T-01 spike and a built-image check on 2026-10-07]**
2. Build args (`ARG NEXT_PUBLIC_API_BASE`): simple, but one image per environment; contradicts D-6.
3. A `/config.js` route the page loads before hydration: works, but adds a request and a global; the provider does the same job with props.
4. Reverse-proxy `/api/*` through the web server so the browser needs no API base: removes the setting but changes the network design (agent network, CORS) beyond this milestone.

## Decision
Option 1 with the `yaml` npm package for the file read. Env (`NEWSDOCK_WEB_*`) overrides the file; defaults equal today's values. The module is server-only; the client sees only the resolved `{apiBaseUrl, pollMs, pageSize}`.

## Consequences
+ One image runs anywhere; same override model as the Python side. − The root layout is dynamically rendered (no static prerender of the shell); acceptable because the feed is client-fetched anyway. − A new npm dependency (`yaml`) and a vitest suite for the loader. − Fetch helpers lose their module-level `API_BASE` constant and take it as an argument.
