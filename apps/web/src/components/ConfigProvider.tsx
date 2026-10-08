"use client";
// Hands the server-resolved runtime config to client components (ADR-0014).
// No data fetching here; the default equals the built-in defaults so isolated
// component tests need no provider.
import { createContext, useContext, type ReactNode } from "react";
import { DEFAULT_CONFIG, type RuntimeConfig } from "@/lib/config/types";

const ConfigContext = createContext<RuntimeConfig>(DEFAULT_CONFIG);

export function ConfigProvider({
  value,
  children,
}: {
  value: RuntimeConfig;
  children: ReactNode;
}) {
  return (
    <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>
  );
}

export function useRuntimeConfig(): RuntimeConfig {
  return useContext(ConfigContext);
}
