# ui-design — Design detail

Reference only; not required reading for approval. Overview: [design.md](design.md).

## 1. Packages (apps/web)

**Spike result (T-01, 2026-10-27) [verified]:** Tailwind 4.3.3, `@tailwindcss/postcss`, shadcn CLI 4.22.1 (`pnpm dlx shadcn@latest init --defaults`) work on Next 16.3.8 / React 19.2.8 / pnpm 12.9.1. `pnpm run build` and `make build APP=web` succeed with no `allowBuilds` change; the container serves `/login` with a stylesheet (`/_next/static/chunks/*.css`, HTTP 200, contains `--primary`, 7.9 kB gzipped on the unstyled base). Deviations from the text below, all applied:
- The CLI default style is `base-nova`, built on **Base UI** (`@base-ui/react`), not Radix `new-york`. Kept: it is the current CLI default and ADR-0022's decision (shadcn primitives) is unchanged. Wherever this file says Radix, read Base UI. AlertDialog comes from `@base-ui/react`.
- The CLI wrote `import { cn } from "cn"` (a third-party npm package `cn`) and `next/font/google` Geist into `layout.tsx`. Both removed: `src/lib/utils.ts` defines `cn` with `clsx` + `tailwind-merge`, and fonts stay the system stack (D-5).
- `shadcn` is a devDependency (its `shadcn/tailwind.css` is imported by `globals.css` at build time). Runtime deps added: `@base-ui/react`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `tw-animate-css`, `next-themes`, `sonner`.
- Built CSS lands in `.next/static/chunks/`, not `.next/static/css/` (Next 16, Turbopack): the AC-14 test follows the `<link>` href instead of a fixed path.
- Re-run `shadcn add` with `--overwrite` and re-apply the `cn` import fix, or the stray `cn` import returns.

Original plan (superseded where noted above):

Runtime: `tailwindcss`, `@tailwindcss/postcss`, `postcss`, `tw-animate-css`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `next-themes`, `sonner`, Radix packages pulled by the added components (`@radix-ui/react-alert-dialog`, `@radix-ui/react-slot`, `@radix-ui/react-label`, `@radix-ui/react-separator`) or the unified `radix-ui` package, whichever the CLI 4.x writes **[assumption]**. Install through `pnpm --dir apps/web add`, never by hand-editing the lockfile. `pnpm-workspace.yaml` `allowBuilds` stays as is unless the install reports a blocked build script; if it does, allow only that package and note it here.

Files added: `postcss.config.mjs`, `components.json` (style `new-york`, `rsc: true`, `tsx: true`, css `src/app/globals.css`, aliases `@/components`, `@/components/ui`, `@/lib/utils`), `src/lib/utils.ts` (`cn`). `lib/api/` untouched.

## 2. Tokens (`src/app/globals.css`)

Structure: `@import "tailwindcss"; @import "tw-animate-css"; @custom-variant dark (&:is(.dark *));` then `:root { ... }` (light), `.dark { ... }`, and `@theme inline { --color-background: var(--background); ... }`.

Semantic set: `background foreground card card-foreground popover popover-foreground primary primary-foreground secondary secondary-foreground muted muted-foreground accent accent-foreground destructive border input ring` plus one extra `primary-text` (green safe for text on `background`) and `success`/`warning` for the live status dot.

Starting values (to be tuned until AC-11 passes) **[assumption]**:

| Token | Light | Dark |
|---|---|---|
| background | near white `#fafafa` | `#0f1210` |
| foreground | `#16201a` | `#eef2ef` |
| primary (buttons, accents) | `#06c755` | `#06c755` |
| primary-foreground | `#052e14` (dark on green) | `#052e14` |
| primary-text | `#047a37` | `#4ade80`-like |
| muted-foreground | `#5b6b61` | `#9aa8a0` |
| border | `#e3e8e5` | `#26302a` |
| radius | `--radius: 0.875rem` (cards `rounded-xl`, buttons `rounded-full` for primary) | same |

Font: `--font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif`. Body 16 px / 1.6; headings tight tracking.

## 3. Layout

- `AppShell`: sticky header (`h-14`, blurred background, bottom border), inner container `max-w-3xl` for feed/article/forms, `max-w-5xl` for tables. `<main id="content">` with a "Skip to content" link first in the DOM.
- Header content: wordmark `newsdock` (green dot + text, a `<span>`), nav links (`aria-current="page"` from `usePathname`), spacer, user area (email hidden below `sm`, role `Badge`, `Log out` ghost button), `ThemeToggle` (icon button, `aria-label="Toggle theme"`). Below `sm` the nav scrolls horizontally inside its own row (`overflow-x-auto`), never the page.
- Host-mismatch alert and the "Cannot reach the server" status render as `Alert` (`role="alert"` / `role="status"` kept).

**As built (T-03, 2026-10-27):** `AppShell` takes the nav as a `nav` prop that `layout.tsx` fills with `features/auth/Nav`, so `components/` imports no feature code. `ThemeToggle` renders both icons and lets CSS pick one (no mounted flag). `<main>` is `max-w-5xl`; the feed, article and form screens narrow themselves to `max-w-3xl` / `max-w-sm` in their own tasks. The host-mismatch notice is an `Alert` passed as `notice`. Tests for `next-themes` must stub `matchMedia` including `addListener`/`removeListener`. Verified in a production build: the server HTML carries the skip link, the toggle and next-themes' inline script (`localStorage`, `prefers-color-scheme`), run before paint.

**As built (T-04, 2026-10-27):** shared `PageHeader`, `EmptyState`, `ErrorAlert`, `ListSkeleton` in `components/`; `features/feed/time.ts` (`timeAgo`, pure, clock injected). The feed shows the skeleton until the first response, then cards or "No articles found"; an error hides both. Two existing assertions changed on purpose (recorded here, nothing else in the old tests moved): `Feed.test.tsx` now expects a badge reading `3 sites` instead of the text `· 3 sites`, and `page.test.tsx` expects the heading "Latest news" because the product name is the shell's wordmark. The Home page wraps the feed in `max-w-3xl`; the filter inputs gained `aria-label`s (Theme, Domain, Title contains) next to their placeholders.

**As built (T-05, 2026-10-27):** `Detail` shows a back link, title, source link, a fields card, themes as badges, sources as a divided list and each analysis as a card with the payload as pretty-printed JSON in a `<pre>` (text only). Loading uses `ListSkeleton`, failure `ErrorAlert`; the old tests were not changed. The article route no longer renders its own `<main>` (the shell has one). Still to fix in later tasks: `login`, `signup`, `live` and `admin/*` pages still wrap their content in `<main>`, which nests inside the shell's `<main>`; each screen's task removes it.

## 4. Screens

| Route | Component | Look |
|---|---|---|
| `/` | `Feed` | filter bar in a `Card` (three `Input`s + `Button`), `ol` of `ArticleItem` cards, "Load more" outline button, `ListSkeleton` while the first fetch is pending |
| (shared) | `ArticleItem` | card: title (link, `line-clamp-3`, `break-words`), meta row (domain, relative time via `Intl.RelativeTimeFormat`, `title` attribute keeps the full date), badges: `N sites` (kept wording), score badges per agent (`title=agent`) |
| `/articles/[id]` | `Detail` | back link, title, meta, themes as badges, analyses as cards; payload rendered in `<pre>` as escaped text |
| `/login`, `/signup` | forms | centered `Card`, max-w-sm, `Label` + `Input`, error `Alert`, pending text on the button |
| `/admin/users` | `Users` | `Table`, role `Badge`, role select kept as native `<select>` styled with input tokens, remove via `AlertDialog` |
| `/admin/agents` | `Agents` | create form, agent rows, key list with `Badge` (active/revoked), revoke via `AlertDialog`, new key in a bordered panel with a Copy button (clipboard, with fallback text selection) |
| `/admin/subscriptions` | `Subscriptions` | `Table` of filters, delete via `AlertDialog` if the screen has delete today |
| `/live` | `Live` | status chip (coloured dot + the existing `STATUS_TEXT` wording, `role="status"` kept; states connecting/live/reconnecting/closed as today, `closed` keeps the Reconnect button), list of `ArticleItem`; new items get `motion-safe:animate-in fade-in slide-in-from-top-2` |

Relative time keeps `new Date(...).toLocaleString()` in the `title` so existing text queries on dates, if any, still have a source; check each test when touching the component.

## 5. Checks

**As built (T-02, 2026-10-27):** `infra/scripts/check_web_style.py [ROOT]` (stdlib only), run by `make style-web`, which `make check-web` depends on; tests in `infra/scripts/tests/rules/test_check_web_style.py` (marker `rules`, no pnpm needed, so they also run in `make test-rules-python`). Comment lines (`//`, `/*`, `*`) are ignored so code may name what it forbids. The text/ring tokens in `globals.css` must be `#rrggbb` (other tokens may use any colour syntax). Final values pass: light text pairs 5.2 to 16.7:1, dark 6.6 to 16.7:1, ring 5.2:1 light and 10.8:1 dark; the radius is 0.875rem. New tokens `--primary-text` and `--destructive-foreground` are mapped in `@theme inline` (`text-primary-text`, `text-destructive-foreground`).

- `infra/scripts/check_web_style.py` (run from `make check-web`, and covered by `make test-rules` with a failing fixture):
  1. Colour literals: regex for `#[0-9a-fA-F]{3,8}\b`, `rgb(`, `hsl(`, `oklch(` and palette classes `\b(bg|text|border|ring|fill|stroke|from|to|via)-(red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone)-\d{2,3}\b` in `apps/web/src/**/*.{ts,tsx,css}` except `app/globals.css`, `components/ui/**`, `lib/api/**` and test files.
  2. Contrast: parse `globals.css` `:root` and `.dark` hex values, compute WCAG ratios for pairs (`foreground/background`, `muted-foreground/background`, `card-foreground/card`, `primary-foreground/primary`, `primary-text/background`, `destructive-foreground/destructive` if present), fail under 4.5.
- Focus ring: `ring` token plus `focus-visible:ring-[3px]` from shadcn; the script also asserts `--ring` differs from `--background` by at least 3:1 (WCAG non-text contrast).
- Manual: screenshots of the 8 routes at 375 and 1280 px, light and dark, saved under `docs/specs/ui-design/screens/` at verify (AC-9, AC-10).
- AC-14: extend the existing image/stack test in `infra/scripts/tests` (scene `images` or `stack`) to fetch `/login`, find the `<link rel="stylesheet">`, fetch it, assert 200 and the token variable name `--primary` in the body.

## 6. Dockerfile

Build stage unchanged (`pnpm install --frozen-lockfile` then `pnpm run build`). Tailwind v4 and lightningcss ship per-platform optional dependencies resolved at install, so building on the same arch inside `node:24-slim` needs no extra step **[assumption; AC-14 proves it]**. Standalone output already copies `.next/static`, where the CSS lands.

## 7. Failure table (full)

| Case | Result |
|---|---|
| `next-themes` storage throws | system theme, no crash |
| JS disabled | light/system CSS via `prefers-color-scheme` is not provided (class strategy); page shows light |
| Reduced motion | no enter animation, no spinner rotation (static dot) |
| Very narrow (320 px) | nav row scrolls inside itself; tables scroll inside a wrapper `overflow-x-auto` |
| Clipboard API denied | Copy button shows "Press Ctrl/Cmd+C" and selects the key text |

## 8. Security

No new data path. Agent payloads and article text remain React text nodes (escaped); no `dangerouslySetInnerHTML` anywhere (add to the style check). Third-party code is limited to packages above; no CDN at run time.

## 9. Extension points (backlog)

Search/filter UI reuses the filter `Card`; story drill-down uses a shadcn `Sheet`; i18n can swap the font stack token.
