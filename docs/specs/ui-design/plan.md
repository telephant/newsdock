# ui-design — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: `tasks/T-NN.md`.

## Plan validation (2026-10-27)

| Check | Result |
|---|---|
| AC → test coverage (AC-1…14 each ≥ 1 TC; no orphan TC) | pass (see tests.md AC coverage) |
| AC → design coverage (design.md table) | pass |
| AC → task coverage (table below) | pass |
| Names consistent (C-1…C-10, F-1…F-3, ADR-0022, script `check_web_style.py`) | pass |
| ADR-0022 Accepted; no Proposed ADR used as decided | pass |
| Scope: nothing from backlog.md (search UI, drill-down, i18n, Storybook) | pass |
| Open design checklist items | none |
| Open risks carried | R-1 Tailwind native binary in `node:24-slim` (T-01 spike, TC-20); R-2 restyle breaking tests (names kept, run suite per task); R-3 contrast of green (T-02 script decides the final shades) |

## Walking skeleton order

**Spike first (T-01):** the biggest unverified claim is that Tailwind v4 + shadcn CLI install and build on Next 16.3 with pnpm 12 and inside the Docker build stage. T-01 proves that before any restyling.

| Task | Title | AC | Phase |
|---|---|---|---|
| T-01 | Spike: Tailwind v4 + shadcn init, build, image build | AC-1, AC-14 (partly) | A foundation. **Done 2026-10-27** (R-1 retired; findings in design-detail §1) |
| T-02 | Tokens and style checks (`check_web_style.py`) | AC-2, AC-11 | A. **Done 2026-10-27** |
| T-03 | Theme, app shell, Nav | AC-3, AC-9 | B skeleton (tokens + shell + feed). **Done 2026-10-27** |
| T-04 | Shared states, Feed, ArticleItem | AC-4, AC-13 | B. **Done 2026-10-27** |
| T-05 | Article detail | AC-5 | C screens. **Done 2026-10-27** |
| T-06 | Login and sign-up | AC-6 | C. **Done 2026-10-27** |
| T-07 | Management screens | AC-7, AC-13 | C. **Done 2026-10-27** |
| T-08 | Live page | AC-8, AC-13 | C. **Done 2026-10-27** |
| T-09 | Image test, screenshots, dark and responsive review | AC-14, AC-9, AC-10 | D proof. **Done 2026-10-27** (3 defects found by eye and fixed; results in tests.md) |
| T-10 | Final checks and docs | AC-12 | D. **Done 2026-10-27** (`make check` exit 0: 449 Python and 159 web tests; diff vs main only in allowed paths; `lib/api` unchanged) |

Milestones: after T-04 the skeleton (tokens + shell + feed) is demonstrable; after T-08 every screen is done; after T-10 the spec is ready for `/spec-verify`.

Rough effort **[assumption]**: A about 1 session, B 1–2, C 2–3, D 1.

## Definition of done (every task)

- Tests written first and seen failing, then green: `pnpm --dir apps/web run test`, `typecheck`, `lint`, `format:check` (and the Python style tests where named).
- No colour literal outside `globals.css` and `components/ui`; accessible names and `role`s unchanged unless the task says so.
- Docs updated when a fact changes (spec status, CLAUDE.md pointer); no secrets.
- Commit per task on the feature branch.

## Out of the plan

Search/filter UI, story drill-down, Storybook, logo/brand, i18n (spec backlog).
