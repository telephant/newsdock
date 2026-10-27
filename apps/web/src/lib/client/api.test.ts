// TC-19 (AC-8): the credentialed API client and its 401 handling.
import { expect, test, vi } from "vitest";
import { apiFetch, apiRequest, type ClientDeps } from "./api";

const CONFIG = { apiBaseUrl: "http://127.0.0.1:8000" };

function deps(
  respond: () => Response | Promise<Response>,
  where = { pathname: "/articles/a", search: "?x=1" },
) {
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
    async () => respond(),
  );
  const navigate = vi.fn();
  const client: ClientDeps = { fetch, navigate, location: () => where };
  return { fetch, navigate, client };
}

const json = (body: unknown, status = 200, headers: HeadersInit = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });

test("every call sends the session cookie and targets the configured base", async () => {
  const { fetch, client } = deps(() => json({ ok: 1 }));
  await apiFetch(CONFIG, "/api/articles?limit=2", undefined, client);
  const [url, init] = fetch.mock.calls[0];
  expect(url).toBe("http://127.0.0.1:8000/api/articles?limit=2");
  expect(init?.credentials).toBe("include");
  expect(init?.method ?? "GET").toBe("GET");
  expect(new Headers(init?.headers).has("content-type")).toBe(false);
});

test("a JSON body is serialized and labelled application/json", async () => {
  const { fetch, client } = deps(() => json({ id: "u" }, 201));
  await apiFetch(
    CONFIG,
    "/api/auth/signup",
    { method: "POST", body: { email: "a@x.io", password: "pw" } },
    client,
  );
  const [, init] = fetch.mock.calls[0];
  expect(init?.method).toBe("POST");
  expect(new Headers(init?.headers).get("content-type")).toBe(
    "application/json",
  );
  expect(init?.body).toBe(JSON.stringify({ email: "a@x.io", password: "pw" }));
  expect(init?.credentials).toBe("include");
});

test("a 401 on a data call sends the user to /login with the page they were on", async () => {
  const { navigate, client } = deps(() =>
    json({ detail: "unauthorized" }, 401),
  );
  const result = await apiRequest(CONFIG, "/api/articles", undefined, client);
  expect(navigate).toHaveBeenCalledWith("/login?next=%2Farticles%2Fa%3Fx%3D1");
  expect(result).toMatchObject({
    kind: "error",
    status: 401,
    detail: "unauthorized",
  });
});

test("a 401 from the login or signup form is a normal answer, not a redirect", async () => {
  for (const path of ["/api/auth/login", "/api/auth/signup"]) {
    const { navigate, client } = deps(() =>
      json({ detail: "invalid_credentials" }, 401),
    );
    const result = await apiRequest(
      CONFIG,
      path,
      { method: "POST", body: {} },
      client,
    );
    expect(navigate).not.toHaveBeenCalled();
    expect(result).toMatchObject({
      kind: "error",
      detail: "invalid_credentials",
    });
  }
});

test("on the login page itself a 401 does not loop", async () => {
  const { navigate, client } = deps(
    () => json({ detail: "unauthorized" }, 401),
    {
      pathname: "/login",
      search: "?next=%2F",
    },
  );
  await apiRequest(CONFIG, "/api/auth/me", undefined, client);
  expect(navigate).not.toHaveBeenCalled();
});

test("a network failure is reported as unreachable and keeps the user on the page", async () => {
  const { navigate, client } = deps(() => {
    throw new TypeError("Failed to fetch");
  });
  const result = await apiRequest(CONFIG, "/api/articles", undefined, client);
  expect(result).toEqual({ kind: "unreachable" });
  expect(navigate).not.toHaveBeenCalled();
});

test("success carries the parsed body; 204 carries none", async () => {
  const ok = deps(() => json({ articles: [] }));
  expect(
    await apiRequest(CONFIG, "/api/articles", undefined, ok.client),
  ).toEqual({
    kind: "ok",
    status: 200,
    data: { articles: [] },
  });
  const empty = deps(() => new Response(null, { status: 204 }));
  expect(
    await apiRequest(
      CONFIG,
      "/api/auth/logout",
      { method: "POST" },
      empty.client,
    ),
  ).toEqual({ kind: "ok", status: 204, data: undefined });
});

test("errors expose the stable code and the retry time", async () => {
  const limited = deps(() =>
    json({ detail: "too_many_attempts" }, 429, { "retry-after": "12" }),
  );
  expect(
    await apiRequest(
      CONFIG,
      "/api/auth/login",
      { method: "POST", body: {} },
      limited.client,
    ),
  ).toEqual({
    kind: "error",
    status: 429,
    detail: "too_many_attempts",
    retryAfter: 12,
  });
  const plain = deps(() => new Response("<html>boom</html>", { status: 502 }));
  expect(
    await apiRequest(CONFIG, "/api/articles", undefined, plain.client),
  ).toEqual({
    kind: "error",
    status: 502,
    detail: "http_502",
    retryAfter: undefined,
  });
});
