// Server-only: resolves the web settings at request time (ADR-0014).
// Order: env NEWSDOCK_WEB_* > file (`common` merged under `web`) > defaults.
// The file is the same newsdock.yaml the Python services read; a bad file never
// breaks the page: it logs and falls back to env, then defaults.
import { readFileSync } from "node:fs";
import { parse } from "yaml";
import { DEFAULT_CONFIG, type RuntimeConfig } from "./types";

type Raw = Record<string, unknown>;

function asObject(value: unknown): Raw {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Raw)
    : {};
}

function loadFile(path: string, read: (path: string) => string): Raw {
  try {
    const doc = asObject(parse(read(path)));
    return { ...asObject(doc.common), ...asObject(doc.web) };
  } catch (error) {
    console.error(
      `newsdock web: cannot use config file ${path}: ${String(error)}`,
    );
    return {};
  }
}

function positiveInt(value: unknown): number | undefined {
  const n = typeof value === "string" ? Number(value) : value;
  return typeof n === "number" && Number.isInteger(n) && n > 0 ? n : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export function resolveConfig(
  env: Record<string, string | undefined>,
  read: (path: string) => string = (path) => readFileSync(path, "utf8"),
): RuntimeConfig {
  const path = env.NEWSDOCK_CONFIG_FILE;
  const file = path ? loadFile(path, read) : {};

  const apiBaseUrl =
    text(env.NEWSDOCK_WEB_API_BASE_URL) ??
    text(file.api_base_url) ??
    DEFAULT_CONFIG.apiBaseUrl;
  return {
    apiBaseUrl: apiBaseUrl.replace(/\/+$/, ""),
    pollMs:
      positiveInt(env.NEWSDOCK_WEB_POLL_MS) ??
      positiveInt(file.poll_ms) ??
      DEFAULT_CONFIG.pollMs,
    pageSize:
      positiveInt(env.NEWSDOCK_WEB_PAGE_SIZE) ??
      positiveInt(file.page_size) ??
      DEFAULT_CONFIG.pageSize,
  };
}

export function getRuntimeConfig(): RuntimeConfig {
  return resolveConfig(process.env);
}
