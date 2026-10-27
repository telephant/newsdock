// TC-20 (AC-8): the page and the API must share a hostname or the cookie is not sent.
import { expect, test } from "vitest";
import { alignHost, describeMismatch, swapHostname } from "./hosts";

test("swapping the hostname keeps the port", () => {
  expect(swapHostname("localhost:3000", "127.0.0.1")).toBe("127.0.0.1:3000");
  expect(swapHostname("127.0.0.1", "localhost")).toBe("localhost");
  expect(swapHostname("[::1]:3000", "localhost")).toBe("localhost:3000");
  expect(swapHostname("localhost:3000", "[::1]")).toBe("[::1]:3000");
  expect(swapHostname("::1", "localhost")).toBe("localhost");
});

test("two loopback aliases that differ redirect to the API's hostname", () => {
  expect(alignHost("localhost", "http://127.0.0.1:8000")).toEqual({
    kind: "redirect",
    hostname: "127.0.0.1",
  });
  expect(alignHost("127.0.0.1", "http://localhost:8000")).toEqual({
    kind: "redirect",
    hostname: "localhost",
  });
});

test("equal hosts need nothing, whatever the ports or case", () => {
  expect(alignHost("localhost", "http://localhost:8000")).toEqual({
    kind: "ok",
  });
  expect(alignHost("LOCALHOST", "http://localhost:8000/")).toEqual({
    kind: "ok",
  });
  expect(alignHost("app.example", "https://app.example:9443")).toEqual({
    kind: "ok",
  });
});

test("the IPv6 loopback counts as a loopback alias", () => {
  expect(alignHost("[::1]", "http://localhost:8000")).toEqual({
    kind: "redirect",
    hostname: "localhost",
  });
  expect(alignHost("::1", "http://[::1]:8000")).toEqual({ kind: "ok" });
});

test("a mismatch that is not between loopback aliases is a configuration error", () => {
  const result = alignHost("app.example", "http://api.other:8000");
  expect(result).toEqual({
    kind: "mismatch",
    requestHost: "app.example",
    apiHost: "api.other",
  });
  // loopback page, remote API: also cross-site, and not safe to redirect to
  expect(alignHost("localhost", "http://api.internal:8000")).toMatchObject({
    kind: "mismatch",
    apiHost: "api.internal",
  });
  expect(alignHost("app.example", "http://127.0.0.1:8000")).toMatchObject({
    kind: "mismatch",
  });
});

test("the mismatch message names both hosts", () => {
  const message = describeMismatch({
    kind: "mismatch",
    requestHost: "app.example",
    apiHost: "api.other",
  });
  expect(message).toContain("app.example");
  expect(message).toContain("api.other");
});

test("an unusable API base or an empty host never breaks the page", () => {
  expect(alignHost("localhost", "not a url")).toEqual({ kind: "ok" });
  expect(alignHost("", "http://localhost:8000")).toEqual({ kind: "ok" });
  expect(alignHost("localhost", "")).toEqual({ kind: "ok" });
});
