"use client";
// Light/dark theme (ADR-0022): next-themes puts a `dark` class on <html> before the
// first paint, from the stored choice or the system setting. No data fetching here.
import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ReactNode } from "react";

export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
