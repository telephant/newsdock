// The optimistic page gate (design C-15). Next's own docs say the proxy is only for
// optimistic checks: it looks at the presence of the session cookie, never at its
// validity. Every data call is authorized by the API, so a forged cookie shows an
// empty shell and gets 401s. Pure; `proxy-handler.ts` applies it to a request.

export type GateInput = {
  pathname: string;
  search: string;
  hasSession: boolean;
  loginRequired?: boolean;
};

const OPEN_EXACT = new Set(["/favicon.ico"]);
const OPEN_PREFIXES = ["/login", "/signup", "/_next"];

function isOpen(pathname: string): boolean {
  if (OPEN_EXACT.has(pathname)) return true;
  return OPEN_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function decideGate(input: GateInput): { redirectTo: string } | null {
  if (input.loginRequired === false) return null;
  if (input.hasSession || isOpen(input.pathname)) return null;
  const back = encodeURIComponent(`${input.pathname}${input.search}`);
  return { redirectTo: `/login?next=${back}` };
}

// Where to go after signing in: only a same-site relative path, never the login
// pages themselves (no loops) and never an absolute or protocol-relative URL.
export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/";
  if (raw.includes("\\") || /[\u0000-\u001f]/.test(raw)) return "/";
  const path = raw.split(/[?#]/)[0];
  if (isOpen(path) && path !== "/favicon.ico" && !path.startsWith("/_next")) {
    return "/";
  }
  return raw;
}
