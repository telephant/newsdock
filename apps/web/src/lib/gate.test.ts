// TC-18 (AC-8): the optimistic page gate, plus the safe `next` target.
import { expect, test } from "vitest";
import { decideGate, safeNext } from "./gate";

test("a visitor without a session cookie is sent to /login with the page to return to", () => {
  expect(decideGate({ pathname: "/", search: "", hasSession: false })).toEqual({
    redirectTo: "/login?next=%2F",
  });
  expect(
    decideGate({
      pathname: "/articles/abc",
      search: "?x=1",
      hasSession: false,
    }),
  ).toEqual({ redirectTo: "/login?next=%2Farticles%2Fabc%3Fx%3D1" });
});

test("a session cookie lets every page through (the API decides the rest)", () => {
  for (const pathname of ["/", "/live", "/admin/users", "/articles/x"]) {
    expect(decideGate({ pathname, search: "", hasSession: true })).toBeNull();
  }
});

test("login, signup and framework files never need a cookie", () => {
  for (const pathname of [
    "/login",
    "/signup",
    "/login/",
    "/_next/static/chunk.js",
    "/_next/image",
    "/favicon.ico",
  ]) {
    expect(decideGate({ pathname, search: "", hasSession: false })).toBeNull();
  }
});

test("look-alike paths are not exempt", () => {
  for (const pathname of ["/login-admin", "/signupx", "/x/login", "/_nextx"]) {
    expect(
      decideGate({ pathname, search: "", hasSession: false }),
    ).not.toBeNull();
  }
});

test("when login is not required (dev mode) the gate never redirects", () => {
  expect(
    decideGate({
      pathname: "/",
      search: "",
      hasSession: false,
      loginRequired: false,
    }),
  ).toBeNull();
});

test("safeNext only accepts a same-site relative path", () => {
  expect(safeNext("/live")).toBe("/live");
  expect(safeNext("/articles/a?x=1&y=2")).toBe("/articles/a?x=1&y=2");
  for (const bad of [
    null,
    undefined,
    "",
    "https://evil.example/",
    "//evil.example",
    "/\\evil.example",
    "javascript:alert(1)",
    "login",
    "/login\n/evil",
  ]) {
    expect(safeNext(bad as string | null | undefined)).toBe("/");
  }
});

test("safeNext never sends someone back to the login page", () => {
  expect(safeNext("/login?next=%2F")).toBe("/");
  expect(safeNext("/signup")).toBe("/");
});
