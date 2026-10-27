# ui-design — Tests

Spec: [spec.md](spec.md) · Design: [design.md](design.md). Test first: write the TC, see it fail, then implement.

## Fixtures and where they live

- Web component tests: vitest + Testing Library next to the component (`*.test.tsx`), existing fetch stubs and `ConfigProvider`/`SessionProvider` helpers. No new fixtures except small article objects built inline (include one CJK title and one 300-character title).
- Style check tests: `infra/scripts/tests/rules/` (pytest) with fixture CSS/TSX snippets written to `tmp_path`; the real tree is checked by `make check-web`.
- Image test: extend the existing `images`/`stack` scene in `infra/scripts/tests/` (needs Docker).

## Test cases

| TC | AC | Level | Case |
|---|---|---|---|
| TC-1 | AC-1 | integration | Given a clean install, When `pnpm --dir apps/web run build` runs, Then it succeeds and `components.json`, `postcss.config.mjs`, `src/app/globals.css` and `src/components/ui/button.tsx` exist |
| TC-2 | AC-2 | unit | Given the real `apps/web/src`, When `check_web_style.py` runs, Then exit 0 (no colour literal, palette class or `dangerouslySetInnerHTML` outside `globals.css`, `components/ui`, `lib/api`, tests) |
| TC-3 | AC-2 | unit | Given a fixture TSX with `bg-green-500`, one with `#06c755` and one with `dangerouslySetInnerHTML`, When the script runs on each, Then each exits non-zero naming the file and line |
| TC-4 | AC-3 | unit | Given a logged-in admin, When `AppShell` + `Nav` render at `/admin/agents`, Then the wordmark text is present and not a link, links are Feed, Live, Agents, Subscriptions, Agents has `aria-current="page"`, email, role badge, "Log out" and "Toggle theme" are present |
| TC-5 | AC-3 | unit | Given viewer and owner sessions, When Nav renders, Then viewer sees Feed and Live only, owner also sees Users (existing Nav tests stay green) |
| TC-6 | AC-4 | unit | Given an article with `source_count` 3, scores and themes, When `ArticleItem` renders, Then title is a link to `/articles/<id>`, domain and a `<time>` element are shown, "3 sites" badge and score badges (title = agent) appear |
| TC-7 | AC-4 | unit | Given a 300-character title and a CJK title, When rendered, Then the title element has wrap classes (`break-words`, `min-w-0`) and `line-clamp-*` |
| TC-8 | AC-5 | unit | Given an analysis payload containing `<img src=x onerror=alert(1)>`, When `Detail` renders, Then the text appears escaped (no `img` element in the DOM) inside Card/Badge layout |
| TC-9 | AC-6 | unit | Given login with a rejected password, When submitted, Then an element with `role="alert"` shows the message inside the form, labels remain, and the submit button is disabled with pending text while the request is in flight |
| TC-10 | AC-7 | unit | Given users, agents and subscriptions data, When rendered, Then each list is a `table` (or rows with the same accessible names), role/status are Badges |
| TC-11 | AC-7 | unit | Given an agent key list, When "Revoke" is clicked, Then a dialog asks to confirm and no request is sent; Cancel sends nothing; Confirm sends the existing revoke request; a newly created key is shown once with a Copy button |
| TC-12 | AC-8 | unit | Given a fake `EventSource`, When it opens, errors (still connecting) and closes, Then the `role="status"` text and a dot's `data-state` follow connecting, live, reconnecting, closed, and "Reconnect" appears when closed |
| TC-13 | AC-8 | unit | Given a new item arrives, When rendered, Then the item carries `motion-safe:` animation classes (none unconditionally) |
| TC-14 | AC-9 | manual | Checklist below M-1 |
| TC-15 | AC-10 | manual | Checklist below M-2 |
| TC-16 | AC-11 | unit | Given the real `globals.css`, When the contrast check runs, Then every listed pair is ≥ 4.5:1 in light and dark and `--ring` vs `--background` ≥ 3:1 |
| TC-17 | AC-11 | unit | Given a fixture CSS with `--muted-foreground` too close to `--background`, When the check runs, Then it exits non-zero naming the pair |
| TC-18 | AC-12 | integration | Given the branch, When `make check-web` runs and `git diff --stat main -- . ':!apps/web' ':!docs' ':!infra/scripts' ':!infra/scripts/tests' ':!Makefile' ':!CLAUDE.md'` is empty and `apps/web/src/lib/api` is unchanged, Then all pass |
| TC-19 | AC-13 | unit | Given Feed with a pending, an empty and a failing fetch, When rendered, Then Skeleton (`data-slot="skeleton"`), an empty-state with text, and `role="alert"` show respectively; same for the live empty state and one management screen |
| TC-20 | AC-14 | integration | Given the built web image running, When `/login` is fetched, Then the HTML has a stylesheet link whose URL returns 200 and contains `--primary` |

## Manual checklists

**M-1 Dark mode (TC-14):** with the OS set to dark, open `/login` in a fresh private window: no light flash on reload (watch with the cache disabled); toggle to light and back; reload keeps the choice; clear storage and reload returns to the system theme; check `/`, `/live`, `/admin/agents` in both.

**M-2 Responsive (TC-15):** for each of `/`, `/articles/<id>`, `/login`, `/signup`, `/live`, `/admin/users`, `/admin/agents`, `/admin/subscriptions` at 375 px and 1280 px, light and dark: no horizontal page scroll, nothing clipped, tap targets usable, tables scroll inside their wrapper only. Save screenshots to `docs/specs/ui-design/screens/`.

**M-3 Taste review (not an AC):** the owner skims the screenshots and notes anything not "modern, readable, clean"; findings go to `verify.md`.

## Results (T-09, 2026-10-27)

Method: the production build served by `next start` (`NEWSDOCK_WEB_LOGIN_REQUIRED=false`, `NEWSDOCK_WEB_API_BASE_URL` pointing at a throwaway mock API with mixed-language, very long and multi-source sample data), driven by headless Chrome through `puppeteer-core` (viewports, `prefers-color-scheme` emulation, console capture). Neither the mock nor the script is in the repo; the run is described here so it can be repeated. Screenshots: `screens/<route>-<width>-<light|dark>.jpg` (8 routes x 375 and 1280 px x 2 themes = 32) and `screens/report.json`.

| Check | Result |
|---|---|
| TC-20 (image serves the stylesheet) | pass: `make test-infra`-style run `pytest -m docker infra/scripts/tests/test_images.py -k stylesheet` against a freshly built `newsdock-web:dev` |
| TC-14 / M-1 dark mode | pass: with a dark system theme the `dark` class is on `<html>` by DOMContentLoaded on all 16 dark page loads (the inline script runs before first paint, so no light flash is possible from the class); toggle flips it, `localStorage.theme` = `dark`, a reload keeps it, the second click returns to light. Cleared-storage fallback to the system theme is covered by the jsdom tests. A frame-by-frame flash recording was not made. |
| TC-15 / M-2 responsive | pass after fixes: 32 of 32 loads have no horizontal page scroll, one `<main>`, and no console warnings or errors. |
| M-3 taste review | done by the author of this change only, owner review still pending: desktop and mobile read clean in both themes. |

Defects found in the first screenshot pass and fixed in T-09 (all by looking at the images; the automated checks had passed):

1. Mobile header: "Subscriptions" was cut to "Sub" and ran into the role badge. Fix: the role badge is hidden below 640 px (like the email), and the link row shows a fade at its right edge as a scroll cue.
2. Users, subscriptions and agent-key tables were crushed to a few characters per column at 375 px, with Delete and Revoke pushed out of view. Fix: the table keeps a minimum width from 640 px up; below that the Created and Last used columns are hidden so the status and action columns fit. Tables still scroll inside their own wrapper if needed.
3. The feed's theme placeholder was clipped on desktop. Fix: shorter placeholder.

## Measurements (provisional targets, not pass/fail)

| What | How |
|---|---|
| First-load CSS size gzipped (target about 50 kB) | `gzip -c .next/static/chunks/*.css | wc -c` after build. **Measured 2026-10-27: 47,644 bytes raw, 9,090 gzipped.** |
| Lighthouse accessibility on `/` and `/login` (target 95+) | Chrome Lighthouse on the running stack. **Not measured**: no Lighthouse tool is installed here; left for `/spec-verify` or the owner. |

## AC coverage

AC-1 TC-1 · AC-2 TC-2, TC-3 · AC-3 TC-4, TC-5 · AC-4 TC-6, TC-7 · AC-5 TC-8 · AC-6 TC-9 · AC-7 TC-10, TC-11 · AC-8 TC-12, TC-13 · AC-9 TC-14 · AC-10 TC-15 · AC-11 TC-16, TC-17 · AC-12 TC-18 · AC-13 TC-19 · AC-14 TC-20.
