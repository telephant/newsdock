// TC-23: runtime config resolves env > file (common + web) > defaults.
import { expect, test, vi } from "vitest";
import { DEFAULT_CONFIG } from "./types";
import { resolveConfig } from "./runtime";

const FILE = "/etc/newsdock/newsdock.yaml";
const yaml = (text: string) => ({
  env: { NEWSDOCK_CONFIG_FILE: FILE } as Record<string, string | undefined>,
  read: () => text,
});

test("defaults match today's values when nothing is set", () => {
  expect(resolveConfig({}, () => "")).toEqual({
    apiBaseUrl: "http://127.0.0.1:8000",
    pollMs: 60000,
    pageSize: undefined,
    sessionCookie: "newsdock_session",
    loginRequired: true,
  });
  expect(resolveConfig({}, () => "")).toEqual(DEFAULT_CONFIG);
});

test("the web section of the file is used", () => {
  const { env, read } = yaml(
    "web:\n  api_base_url: http://f:1\n  poll_ms: 5000\n  page_size: 30\n",
  );
  expect(resolveConfig(env, read)).toEqual({
    apiBaseUrl: "http://f:1",
    pollMs: 5000,
    pageSize: 30,
    sessionCookie: "newsdock_session",
    loginRequired: true,
  });
});

test("common keys are inherited and the web section overrides them", () => {
  const { env, read } = yaml(
    "common:\n  poll_ms: 1000\n  api_base_url: http://common:1\n" +
      "web:\n  api_base_url: http://web:2\n",
  );
  const config = resolveConfig(env, read);
  expect(config.apiBaseUrl).toBe("http://web:2");
  expect(config.pollMs).toBe(1000);
});

test("env beats the file", () => {
  const { env, read } = yaml(
    "web:\n  api_base_url: http://f:1\n  poll_ms: 5000\n",
  );
  const config = resolveConfig(
    {
      ...env,
      NEWSDOCK_WEB_API_BASE_URL: "http://env:9/",
      NEWSDOCK_WEB_POLL_MS: "7000",
    },
    read,
  );
  expect(config.apiBaseUrl).toBe("http://env:9"); // trailing slash trimmed
  expect(config.pollMs).toBe(7000);
});

test("an unreadable or invalid file falls back to env then defaults", () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  const failing = () => {
    throw new Error("ENOENT");
  };
  const config = resolveConfig(
    { NEWSDOCK_CONFIG_FILE: FILE, NEWSDOCK_WEB_API_BASE_URL: "http://env:9" },
    failing,
  );
  expect(config.apiBaseUrl).toBe("http://env:9");
  expect(config.pollMs).toBe(60000);
  const broken = resolveConfig({ NEWSDOCK_CONFIG_FILE: FILE }, () => "web: [x");
  expect(broken).toEqual(DEFAULT_CONFIG);
  expect(error).toHaveBeenCalled();
  error.mockRestore();
});

test("bad numbers fall back to the defaults", () => {
  const { env, read } = yaml("web:\n  poll_ms: -5\n  page_size: lots\n");
  const config = resolveConfig(env, read);
  expect(config.pollMs).toBe(60000);
  expect(config.pageSize).toBeUndefined();
});

// ui-login T-10 (AC-8): the gate needs the API's cookie name and whether login is on
test("session_cookie and login_required come from env, then the file", () => {
  const { env, read } = yaml(
    "web:\n  session_cookie: file_sid\n  login_required: false\n",
  );
  expect(resolveConfig(env, read)).toMatchObject({
    sessionCookie: "file_sid",
    loginRequired: false,
  });
  const config = resolveConfig(
    {
      ...env,
      NEWSDOCK_WEB_SESSION_COOKIE: "env_sid",
      NEWSDOCK_WEB_LOGIN_REQUIRED: "true",
    },
    read,
  );
  expect(config.sessionCookie).toBe("env_sid");
  expect(config.loginRequired).toBe(true);
});

test("login_required understands the usual spellings and ignores nonsense", () => {
  for (const [raw, expected] of [
    ["false", false],
    ["FALSE", false],
    ["0", false],
    ["no", false],
    ["true", true],
    ["1", true],
    ["maybe", true], // unusable: the safe default is to require login
    ["", true],
  ] as const) {
    const config = resolveConfig(
      { NEWSDOCK_WEB_LOGIN_REQUIRED: raw },
      () => "",
    );
    expect(config.loginRequired, raw).toBe(expected);
  }
});

test("an empty cookie name falls back to the default", () => {
  const config = resolveConfig({ NEWSDOCK_WEB_SESSION_COOKIE: "  " }, () => "");
  expect(config.sessionCookie).toBe("newsdock_session");
});
