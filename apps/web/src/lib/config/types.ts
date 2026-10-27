// Shape of the settings the browser needs (ADR-0014). Client-safe: no server imports.
export type RuntimeConfig = {
  apiBaseUrl: string;
  pollMs: number;
  pageSize: number | undefined;
  // ui-login (ADR-0020/0021): the gate checks this cookie, which the API sets; it
  // must equal the api section's auth_cookie_name
  sessionCookie: string;
  // false = dev mode: the API is open (api.auth_required false), so nothing is gated
  loginRequired: boolean;
};

// Equal to the values hardcoded before externalize-config (AC-4 for the web app).
export const DEFAULT_CONFIG: RuntimeConfig = {
  apiBaseUrl: "http://127.0.0.1:8000",
  pollMs: 60_000,
  pageSize: undefined,
  sessionCookie: "newsdock_session",
  loginRequired: true,
};
