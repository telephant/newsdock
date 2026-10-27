# ui-design — Verify

Verified 2026-10-27 on branch `worktree-roadmap-ui-design`. **Verdict: pass with follow-ups.** All 14 ACs hold; the two manual ones (AC-9, AC-10) were run on the production build. Open items are measurements and reviews that need a person or a wider setup, listed at the end.

## Commands run (this session)

| Command | Result |
|---|---|
| `make check` (style-web, lint, format, types, web tests, Python lint/types/import/layout/config checks, Python tests, docs check) | exit 0; 449 Python tests passed (222 docker/rules deselected by design), 22 web test files and 159 web tests passed |
| `make test-rules` (includes pnpm-dependent rule tests and the 14 style-check tests) | exit 0; 37 passed |
| `make test-infra SCENE=images` (builds all 6 images; includes TC-20) | exit 0; 14 passed (run twice: before and after the verify clean-up) |
| `make setup-web` (frozen lockfile) then `pnpm --dir apps/web run build` | exit 0; build compiled |
| `git diff --stat main` outside `apps/web`, `docs`, `infra/scripts`, `Makefile`, `CLAUDE.md` | empty; `apps/web/src/lib/api` diff empty |

## Results by acceptance criterion

| AC | TC | Result | Evidence |
|---|---|---|---|
| AC-1 design system installed | TC-1 | pass | `src/design-system.test.ts`; `pnpm run build` and `make build APP=web` succeed; `components.json`, `postcss.config.mjs`, `globals.css`, `components/ui/*` present |
| AC-2 tokens only | TC-2, TC-3 | pass | `check_web_style.py` exits 0 on the real tree; 5 fixture cases (palette class, hex, `rgb()`, arbitrary hex, raw HTML) fail it; exemptions and comment handling tested |
| AC-3 app shell | TC-4, TC-5 | pass | `AppShell.test.tsx` (wordmark not a link, role links, `aria-current`, user area, toggle, skip link, host notice); the original Nav tests unchanged and green. Below 640 px the email and role badge are hidden (spec amended) |
| AC-4 feed cards | TC-6, TC-7 | pass | `ArticleItem.test.tsx` (link, `<time>`, "N sites" badge, score badges, long and Japanese titles wrap and clamp) |
| AC-5 article detail | TC-8 | pass | `Detail.test.tsx`: payload with `<img onerror>` stays text in a `<pre>`, no `img` created |
| AC-6 auth forms | TC-9 | pass | login and sign-up tests: inline `role="alert"` inside the form, `aria-invalid` and `aria-describedby` on both fields, pending button text and `aria-busy` |
| AC-7 management screens | TC-10, TC-11 | pass | tables, badges, `AlertDialog` flows (cancel sends nothing, confirm deletes or revokes), one-time key card with Copy; `ConfirmDialog.test.tsx` |
| AC-8 live page | TC-12, TC-13 | pass | `data-state` follows connecting, live, reconnecting, closed; items carry only `motion-safe:` animation classes; the built CSS contains `motion-safe:animate-in` |
| AC-9 dark mode | TC-14 (manual M-1) | manual-ok | Production build in headless Chrome: on all 16 dark-scheme loads the `dark` class was on `<html>` by DOMContentLoaded; toggle flips it, `localStorage.theme` = `dark`, a reload keeps it, a second click returns to light. Not recorded frame by frame |
| AC-10 responsive | TC-15 (manual M-2) | manual-ok | 8 routes x 375 and 1280 px x light and dark = 32 loads: no horizontal page scroll, one `<main>`, no console warnings or errors. Screenshots and `report.json` in `screens/` (re-taken at verify) |
| AC-11 accessibility basics | TC-16, TC-17 | pass | contrast script: every text pair at least 5.2:1 in both themes, ring at least 5.2:1 against the background; low-contrast and weak-ring fixtures fail |
| AC-12 no behaviour change | TC-18 | pass | `make check` exit 0; diff outside the allowed paths empty; `lib/api` unchanged. Original screen tests were not changed except two assertions recorded in design-detail (a `3 sites` badge instead of `· 3 sites`; page heading "Latest news") |
| AC-13 loading, empty, error | TC-19 | pass | feed, article, users, agents, subscriptions and live tests for skeleton, empty state and `role="alert"` |
| AC-14 container still works | TC-20 | pass | `test_web_image_ships_the_stylesheet` against a freshly built image: `/login` links a CSS file, HTTP 200, contains `--primary` |

## Measurements (provisional targets, not ACs)

| What | Target | Measured |
|---|---|---|
| First-load CSS, gzipped | about 50 kB | 8,977 bytes gzipped (47,181 raw) |
| Lighthouse accessibility, `/` and `/login`, mobile and desktop | 95 or more | 100 on all four runs, no failed audits (Lighthouse 13.5.0 on the production build against the mock API, light theme) |

## Doc drift and scope

Fixed at verify:

- `sonner` and `separator` were installed (listed in the spec's scope) but nothing used them: toasts were never needed because every screen reports results inline. Removed the two generated files and the `sonner` dependency; spec, design, design-detail and the web README now say so. `make check` and the image scene were re-run afterwards.
- `design.md` component table did not mention `ConfirmDialog`, `CredentialForm` or `time.ts`; added.
- Earlier drift already recorded: Base UI instead of Radix (ADR-0022 amendment), the local `cn`, inline user area instead of a dropdown, mobile hiding of email, badge and timestamp columns.

Checked and clean: names in `design.md` match the code; ADR-0022 is accurate and not Proposed; the web README run steps work from a clean install; nothing from `backlog.md` (search UI, drill-down, i18n, Storybook) was built.

## Follow-ups (moved to `backlog.md`)

1. Owner review of the screenshots (the "nice" call is subjective; only the implementer has looked).
2. Card layout for tables on phones; the timestamp columns are hidden below 640 px today.
3. Verified in Chrome only; repeat in Safari and Firefox (dark-mode first paint, `mask-image`, `Intl.RelativeTimeFormat`).
4. The review ran against a mock API; a hand run on the real stack (`make up`, real login cookie, real GDELT data) was not done.
5. Dark-theme Lighthouse run and a frame-by-frame check for a theme flash.
6. Commit the screenshot script or move it to Playwright so the review is repeatable.
