// What the proxy does with a request: align the hostname with the API's, then apply
// the optimistic login gate. Kept out of `src/proxy.ts` so it can be tested with
// a plain NextRequest and an explicit config.
//
// The `Host` header is the source of truth for the page's hostname: NextURL rewrites
// 127.0.0.1 to localhost, which would hide exactly the mismatch this has to see.
import { NextResponse, type NextRequest } from "next/server";
import type { RuntimeConfig } from "@/lib/config/types";
import { decideGate } from "@/lib/gate";
import {
  alignHost,
  describeMismatch,
  MISMATCH_HEADER,
  swapHostname,
} from "@/lib/hosts";

export { MISMATCH_HEADER };

export function handleRequest(
  request: NextRequest,
  config: RuntimeConfig,
): NextResponse {
  const host = request.headers.get("host") ?? request.nextUrl.host;
  const origin = `${request.nextUrl.protocol}//${host}`;
  const { pathname, search } = request.nextUrl;

  const check = alignHost(host, config.apiBaseUrl);
  if (check.kind === "redirect") {
    const there = swapHostname(host, check.hostname);
    return NextResponse.redirect(
      new URL(`${request.nextUrl.protocol}//${there}${pathname}${search}`),
    );
  }

  const verdict = decideGate({
    pathname,
    search,
    hasSession: Boolean(request.cookies.get(config.sessionCookie)?.value),
    loginRequired: config.loginRequired,
  });
  if (verdict) {
    return NextResponse.redirect(new URL(verdict.redirectTo, origin));
  }

  const headers = new Headers(request.headers);
  if (check.kind === "mismatch") {
    headers.set(MISMATCH_HEADER, describeMismatch(check));
  } else {
    headers.delete(MISMATCH_HEADER);
  }
  return NextResponse.next({ request: { headers } });
}
