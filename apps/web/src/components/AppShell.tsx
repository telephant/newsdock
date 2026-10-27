// Page frame (ADR-0022): skip link, sticky header (wordmark, nav, theme toggle) and
// the main landmark. Pages choose their own reading width inside <main>.
import type { ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import { ThemeToggle } from "./ThemeToggle";

// `nav` is a slot filled by the layout (features/auth/Nav): shared components do not
// import feature code.
export function AppShell({
  nav,
  children,
  notice,
}: {
  nav: ReactNode;
  children: ReactNode;
  notice?: string | null;
}) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#content"
        className="sr-only focus-visible:not-sr-only focus-visible:absolute focus-visible:top-2 focus-visible:left-2 focus-visible:z-50 focus-visible:rounded-full focus-visible:bg-background focus-visible:px-4 focus-visible:py-2 focus-visible:ring-3 focus-visible:ring-ring"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2 sm:flex-nowrap">
          <span className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <span aria-hidden className="size-2.5 rounded-full bg-primary" />
            newsdock
          </span>
          <div className="order-last w-full min-w-0 sm:order-none sm:w-auto sm:flex-1">
            {nav}
          </div>
          <div className="ml-auto sm:ml-0">
            <ThemeToggle />
          </div>
        </div>
      </header>
      {notice ? (
        <div className="mx-auto w-full max-w-5xl px-4 pt-4">
          <Alert variant="destructive">{notice}</Alert>
        </div>
      ) : null}
      <main id="content" className="mx-auto w-full max-w-5xl px-4 py-8">
        {children}
      </main>
    </div>
  );
}
