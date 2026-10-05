# ADR-0009: Web toolchain (ESLint, Prettier, Vitest) and Node pinned by pnpm

Status: **Accepted 2026-10-05** (user decision in `/spec-design foundation`)

## Context
`apps/web` needs lint, format check, type check and a smoke test under `make check`, and a reproducible Node. The installed Node is 26.9.0 (Current, not LTS); LTS lines are 24 "Krypton" and 22 **[verified]**. Next.js 16 removed `next lint`; `create-next-app` offers ESLint, Biome or no linter **[verified, docs search]**.

## Options
Lint/format: (a) ESLint + `eslint-config-next` 16.3.8 + Prettier 3.9.9; (b) Biome. Tests: Vitest 5.0.3 + Testing Library 16.3.3. Node pin: (i) pnpm `devEngines.runtime` (`node 24.x`, `onFail: download`; resolved version in the lockfile) **[verified, pnpm docs search]**; (ii) `.node-version` + nvm/fnm; (iii) Homebrew `node@24`. Versions **[verified, npm]**.

## Decision
(a) + Vitest + (i). ESLint with Next's config is the `create-next-app` default and familiar to a frontend engineer; Prettier supplies the format check required by AC-4. Dockerfile base is `node:24-slim` **[verified tag]**. **Versions after the T-02 spike (2026-10-05) [verified]:** `typescript` stays at `^5` (scaffold: 5.9.3) and `eslint` at `^9` (scaffold: 9.39.5). TypeScript 7.0.2 passes `tsc` and `next build` but breaks `typescript-eslint` (peer range `<6.1.0`); ESLint 10.12.0 breaks `eslint-config-next` 16.3.8. Revisit when those packages support them. Node 24.21.0 via `devEngines.runtime`, Vitest 5.0.3, Testing Library 16.3.3 and jsdom were run successfully.

## Consequences
+ No version manager to install; CI and Docker use the same Node line (pnpm runtime feature verified in T-02). − Two tools for lint and format instead of one; TypeScript and ESLint are held one major behind the latest until the Next.js lint config catches up.
