// Shape of the settings the browser needs (ADR-0014). Client-safe: no server imports.
export type RuntimeConfig = {
  apiBaseUrl: string;
  pollMs: number;
  pageSize: number | undefined;
};

// Equal to the values hardcoded before externalize-config (AC-4 for the web app).
export const DEFAULT_CONFIG: RuntimeConfig = {
  apiBaseUrl: "http://127.0.0.1:8000",
  pollMs: 60_000,
  pageSize: undefined,
};
