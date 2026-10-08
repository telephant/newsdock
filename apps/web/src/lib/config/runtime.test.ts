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
