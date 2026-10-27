# ui-design — Design detail

Reference only; not required reading for approval. Overview: [design.md](design.md).

## 1. Packages (apps/web)

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

- `infra/scripts/check_web_style.py` (run from `make check-web`, and covered by `make test-rules` with a failing fixture):
  1. Colour literals: regex for `#[0-9a-fA-F]{3,8}\b`, `rgb(`, `hsl(`, `oklch(` and palette classes `\b(bg|text|border|ring|fill|stroke|from|to|via)-(red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone)-\d{2,3}\b` in `apps/web/src/**/*.{ts,tsx,css}` except `app/globals.css`, `components/ui/**`, `lib/api/**` and test files.
  2. Contrast: parse `globals.css` `:root` and `.dark` hex values, compute WCAG ratios for pairs (`foreground/background`, `muted-foreground/background`, `card-foreground/card`, `primary-foreground/primary`, `primary-text/background`, `destructive-foreground/destructive` if present), fail under 4.5.
- Focus ring: `ring` token plus `focus-visible:ring-[3px]` from shadcn; the script also asserts `--ring` differs from `--background` by at least 3:1 (WCAG non-text contrast).
- Manual: screenshots of the 8 routes at 375 and 1280 px, light and dark, saved under `docs/specs/ui-design/screens/` at verify (AC-9, AC-10).
- AC-14: extend the existing image/stack test in `infra/tests` (scene `images` or `stack`) to fetch `/login`, find the `<link rel="stylesheet">`, fetch it, assert 200 and the token variable name `--primary` in the body.

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
