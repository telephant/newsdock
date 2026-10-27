// Browser-side API access (ADR-0021): the API is called directly, with the session
// cookie. Types come from the generated `lib/api` (never hand-edited); this wrapper
// only adds credentials, JSON bodies and the sign-in redirect on a 401.

export type ApiTarget = { apiBaseUrl: string };

export type RequestInitLite = {
  method?: string;
  body?: unknown; // serialized as JSON
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

// Seams for tests; the defaults use the browser.
export type ClientDeps = {
  fetch?: (url: string, init?: RequestInit) => Promise<Response>;
  navigate?: (url: string) => void;
  location?: () => { pathname: string; search: string };
};

export type ApiResult<T> =
  | { kind: "ok"; status: number; data: T }
  | {
      kind: "error";
      status: number;
      detail: string; // the API's stable code, e.g. "invalid_credentials"
      retryAfter: number | undefined;
    }
  | { kind: "unreachable" };

// These two routes answer 401 as an ordinary result of a form, not a lost session.
const FORM_PATHS = ["/api/auth/login", "/api/auth/signup"];
const SIGN_IN_PAGES = ["/login", "/signup"];

export class ApiUnreachable extends Error {
  constructor() {
    super("the API cannot be reached");
  }
}

function defaultNavigate(url: string): void {
  window.location.assign(url);
}

function defaultLocation(): { pathname: string; search: string } {
  return { pathname: window.location.pathname, search: window.location.search };
}

export async function apiFetch(
  target: ApiTarget,
  path: string,
  init: RequestInitLite = {},
  deps: ClientDeps = {},
): Promise<Response> {
  const doFetch =
    deps.fetch ?? ((url, options) => globalThis.fetch(url, options));
  const headers = new Headers(init.headers);
  let body: string | undefined;
  if (init.body !== undefined) {
    headers.set("content-type", "application/json");
    body = JSON.stringify(init.body);
  }
  let response: Response;
  try {
    response = await doFetch(`${target.apiBaseUrl}${path}`, {
      method: init.method ?? "GET",
      headers,
      body,
      credentials: "include", // the session cookie rides along (cross-origin, ADR-0021)
      signal: init.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiUnreachable();
  }
  if (response.status === 401 && !FORM_PATHS.some((p) => path.startsWith(p))) {
    const here = (deps.location ?? defaultLocation)();
    if (!SIGN_IN_PAGES.includes(here.pathname)) {
      const back = encodeURIComponent(`${here.pathname}${here.search}`);
      (deps.navigate ?? defaultNavigate)(`/login?next=${back}`);
    }
  }
  return response;
}

async function detailOf(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    // not JSON (a proxy error page): fall through to the status code
  }
  return `http_${response.status}`;
}

export async function apiRequest<T>(
  target: ApiTarget,
  path: string,
  init?: RequestInitLite,
  deps?: ClientDeps,
): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await apiFetch(target, path, init, deps);
  } catch (error) {
    if (error instanceof ApiUnreachable) return { kind: "unreachable" };
    throw error;
  }
  if (!response.ok) {
    const retry = Number(response.headers.get("retry-after"));
    return {
      kind: "error",
      status: response.status,
      detail: await detailOf(response),
      retryAfter: Number.isFinite(retry) && retry > 0 ? retry : undefined,
    };
  }
  if (response.status === 204) {
    return { kind: "ok", status: 204, data: undefined as T };
  }
  return {
    kind: "ok",
    status: response.status,
    data: (await response.json()) as T,
  };
}
