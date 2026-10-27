// TC-18 and TC-20 together: what the proxy does with a real NextRequest.
import { NextRequest } from "next/server";
import { expect, test } from "vitest";
import { DEFAULT_CONFIG, type RuntimeConfig } from "./config/types";
import { handleRequest, MISMATCH_HEADER } from "./proxy-handler";

const config = (over: Partial<RuntimeConfig> = {}): RuntimeConfig => ({
  ...DEFAULT_CONFIG, // api http://127.0.0.1:8000, cookie newsdock_session
  ...over,
});

// A real server request carries the Host header the browser used; NextURL cannot
// be trusted for it (it rewrites 127.0.0.1 to localhost).
function request(
  url: string,
  cookie?: string,
  extra: Record<string, string> = {},
): NextRequest {
  const headers: Record<string, string> = { host: new URL(url).host, ...extra };
  if (cookie) headers.cookie = cookie;
  return new NextRequest(url, { headers });
}

test("no cookie: redirected to /login with the page to return to", () => {
  const response = handleRequest(
    request("http://127.0.0.1:3000/articles/a?x=1"),
    config(),
  );
  expect(response.status).toBe(307);
  const location = new URL(response.headers.get("location") ?? "");
  expect(location.origin).toBe("http://127.0.0.1:3000");
  expect(location.pathname).toBe("/login");
  expect(location.searchParams.get("next")).toBe("/articles/a?x=1");
});

test("the configured cookie name is the one that counts", () => {
  const url = "http://127.0.0.1:3000/";
  const named = config({ sessionCookie: "my_sid" });
  expect(
    handleRequest(request(url, "newsdock_session=abc"), named).status,
  ).toBe(307);
  const passed = handleRequest(request(url, "my_sid=abc"), named);
  expect(passed.status).toBe(200);
  expect(passed.headers.get("location")).toBeNull();
});

test("an empty cookie value is no session", () => {
  const response = handleRequest(
    request("http://127.0.0.1:3000/", "newsdock_session="),
    config(),
  );
  expect(response.status).toBe(307);
});

test("login and static paths pass without a cookie", () => {
  for (const path of [
    "/login",
    "/signup",
    "/_next/static/a.js",
    "/favicon.ico",
  ]) {
    const response = handleRequest(
      request(`http://127.0.0.1:3000${path}`),
      config(),
    );
    expect(response.status, path).toBe(200);
  }
});

test("a page on localhost with the API on 127.0.0.1 is redirected to 127.0.0.1, same path and port", () => {
  const response = handleRequest(
    request("http://localhost:3000/articles/a?x=1", "newsdock_session=abc"),
    config(),
  );
  expect(response.status).toBe(307);
  expect(response.headers.get("location")).toBe(
    "http://127.0.0.1:3000/articles/a?x=1",
  );
});

test("host alignment happens before the login gate, also for /login", () => {
  const response = handleRequest(
    request("http://localhost:3000/login"),
    config(),
  );
  expect(response.headers.get("location")).toBe("http://127.0.0.1:3000/login");
});

test("a non-loopback mismatch is reported to the layout, never trusted from the client", () => {
  const cfg = config({ apiBaseUrl: "http://api.other:8000" });
  const response = handleRequest(request("http://app.example:3000/login"), cfg);
  expect(response.status).toBe(200);
  const forwarded = response.headers.get(
    `x-middleware-request-${MISMATCH_HEADER}`,
  );
  expect(forwarded).toContain("app.example");
  expect(forwarded).toContain("api.other");

  // a client that sends the header itself gets it removed when nothing mismatches
  const spoof = request("http://127.0.0.1:3000/login", undefined, {
    [MISMATCH_HEADER]: "forged",
  });
  const clean = handleRequest(spoof, config());
  expect(
    clean.headers.get(`x-middleware-request-${MISMATCH_HEADER}`),
  ).toBeNull();
  expect(
    clean.headers.get("x-middleware-override-headers") ?? "",
  ).not.toContain("forged");
});

test("when login is not required nothing is gated", () => {
  const response = handleRequest(
    request("http://127.0.0.1:3000/live"),
    config({ loginRequired: false }),
  );
  expect(response.status).toBe(200);
});
