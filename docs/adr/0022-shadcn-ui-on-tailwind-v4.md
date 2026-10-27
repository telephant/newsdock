# ADR-0022: Style the web UI with shadcn/ui on Tailwind CSS v4

Status: **Accepted 2026-10-27** (the user asked for shadcn/ui when starting `ui-design`; the token and theming details below were confirmed by default at /spec-design)

## Context
`apps/web` is unstyled HTML (about 2,400 lines of TSX, 8 routes). The owner wants a modern, clean, readable UI in the spirit of the LINE website, and named shadcn/ui. The repo rules say `components/` is shared UI without data fetching and `lib/api/` is generated.

## Options
1. **shadcn/ui on Tailwind v4** (component source copied into `src/components/ui`, Radix primitives, CSS-variable tokens).
2. A packaged kit (MUI, Chakra, Mantine): runtime dependency, heavier, harder to give a custom look.
3. Hand-written CSS modules: no new dependency, but we rebuild dialogs, focus handling and tokens ourselves.

## Decision
Option 1. Tokens live in one `globals.css` (light and dark sets, `@theme inline` mapping), theming via `next-themes` with the `class` strategy and a system default, icons from `lucide-react`, system fonts only (no web-font fetch). Colours outside `globals.css` and `components/ui` must be semantic token classes; `make check-web` enforces it and checks contrast.

**Amendment 2026-10-27 (T-01 spike):** the current shadcn CLI default style (`base-nova`) builds on Base UI instead of Radix; we keep the default. The generated `cn` import from the `cn` npm package is replaced with a local `cn` (`clsx` + `tailwind-merge`) to avoid an unnecessary third-party dependency.

## Consequences
+ Accessible primitives and a consistent look without a runtime UI library; the code is ours to edit. + Tokens make the green accent and dark mode a one-file change.
− Adds Tailwind, PostCSS and about eight packages to `apps/web`; the image build needs Tailwind's native binary. − Generated `ui/*` files need lint/format allowances and should be edited sparingly so the CLI can refresh them. − Restyling can break tests that query by markup; names and roles are kept.
