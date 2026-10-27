// Host alignment (ADR-0021, design C-15). The session cookie belongs to a hostname,
// not a port: a page on `localhost:3000` that calls the API on `127.0.0.1:8000` is
// cross-site, so the cookie would never come back. Pure; the proxy acts on it.

// Request header the proxy sets for the layout when page and API hosts cannot be
// reconciled. The proxy always overwrites or removes it, so a client cannot forge it.
export const MISMATCH_HEADER = "x-newsdock-host-mismatch";

export type HostCheck =
  | { kind: "ok" }
  | { kind: "redirect"; hostname: string } // switch the page to the API's host
  | { kind: "mismatch"; requestHost: string; apiHost: string }; // cannot be fixed here

const LOOPBACK = new Set(["localhost", "127.0.0.1", "::1"]);

function hostnameOf(host: string): string {
  const trimmed = host.trim().toLowerCase();
  if (trimmed.startsWith("[")) return trimmed.slice(1, trimmed.indexOf("]")); // [::1]:3000
  if ((trimmed.match(/:/g) ?? []).length > 1) return trimmed; // bare IPv6
  return trimmed.split(":")[0];
}

function apiHostname(apiBaseUrl: string): string | null {
  try {
    return hostnameOf(new URL(apiBaseUrl).hostname);
  } catch {
    return null; // an unusable base never breaks the page
  }
}

export function alignHost(requestHost: string, apiBaseUrl: string): HostCheck {
  const page = hostnameOf(requestHost);
  const api = apiHostname(apiBaseUrl);
  if (!page || !api || page === api) return { kind: "ok" };
  if (LOOPBACK.has(page) && LOOPBACK.has(api)) {
    return { kind: "redirect", hostname: api === "::1" ? "[::1]" : api };
  }
  return { kind: "mismatch", requestHost: page, apiHost: api };
}

// "localhost:3000" + "127.0.0.1" -> "127.0.0.1:3000" (the port stays)
export function swapHostname(host: string, hostname: string): string {
  const trimmed = host.trim();
  const closing = trimmed.indexOf("]");
  const afterName = closing >= 0 ? trimmed.slice(closing + 1) : trimmed;
  const colon = afterName.lastIndexOf(":");
  const bareIpv6 = closing < 0 && (trimmed.match(/:/g) ?? []).length > 1;
  const port = !bareIpv6 && colon >= 0 ? afterName.slice(colon) : "";
  return `${hostname}${port}`;
}

export function describeMismatch(
  check: Extract<HostCheck, { kind: "mismatch" }>,
): string {
  return (
    `Configuration error: this page is served from "${check.requestHost}" but the ` +
    `API is at "${check.apiHost}". The login cookie is only sent to the host that ` +
    "set it, so signing in cannot work. Serve both from the same hostname " +
    "(web.api_base_url in infra/config/newsdock.yaml)."
  );
}
