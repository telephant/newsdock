// TC-31 (AC-12): every agent's saved filters, with delete for admins.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Subscriptions } from "./Subscriptions";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

type Handler = (init?: RequestInit) => Response | Promise<Response>;

function stub(routes: Record<string, Handler>) {
  const fetchMock = vi.fn<
    (url: string, init?: RequestInit) => Promise<Response>
  >(async (url, init) => {
    const key = `${init?.method ?? "GET"} ${new URL(url).pathname}`;
    const handler = routes[key];
    if (!handler) throw new Error(`unexpected request: ${key}`);
    return handler(init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const SUBS = [
  {
    id: "s1",
    agent_id: "a1",
    agent_name: "alpha",
    filter: { theme: "ECON_*", domain: "example.com" },
    created_at: "2026-10-27T10:00:00Z",
  },
  {
    id: "s2",
    agent_id: "a2",
    agent_name: "beta",
    filter: {},
    created_at: "2026-10-27T11:00:00Z",
  },
];

test("shows each subscription with its agent and filter fields", async () => {
  stub({ "GET /api/admin/subscriptions": () => json(SUBS) });
  render(<Subscriptions />);
  await screen.findByText("alpha");
  expect(screen.getByText("beta")).toBeTruthy();
  expect(screen.getByText("theme: ECON_*")).toBeTruthy();
  expect(screen.getByText("domain: example.com")).toBeTruthy();
  expect(screen.getByText(/any article/i)).toBeTruthy(); // beta's empty filter
});

test("deleting asks first, calls the route and removes the row", async () => {
  const fetchMock = stub({
    "GET /api/admin/subscriptions": () => json(SUBS),
    "DELETE /api/admin/subscriptions/s1": () =>
      new Response(null, { status: 204 }),
  });
  const confirm = vi.fn(() => true);
  render(<Subscriptions confirm={confirm} />);
  await screen.findByText("alpha");
  fireEvent.click(
    screen.getByRole("button", { name: "Delete subscription of alpha" }),
  );
  await vi.waitFor(() => expect(screen.queryByText("alpha")).toBeNull());
  expect(screen.getByText("beta")).toBeTruthy();
  expect(String(confirm.mock.calls[0])).toContain("alpha");
  const del = fetchMock.mock.calls.find(
    ([, init]) => init?.method === "DELETE",
  );
  expect(new URL(del?.[0] ?? "").pathname).toBe("/api/admin/subscriptions/s1");
  expect(del?.[1]?.credentials).toBe("include");
});

test("cancelling the confirmation keeps the row and sends nothing", async () => {
  const fetchMock = stub({ "GET /api/admin/subscriptions": () => json(SUBS) });
  render(<Subscriptions confirm={() => false} />);
  await screen.findByText("alpha");
  fireEvent.click(
    screen.getByRole("button", { name: "Delete subscription of alpha" }),
  );
  expect(screen.getByText("alpha")).toBeTruthy();
  expect(
    fetchMock.mock.calls.filter(([, i]) => i?.method === "DELETE"),
  ).toHaveLength(0);
});

test("a subscription that is already gone (404) just disappears", async () => {
  stub({
    "GET /api/admin/subscriptions": () => json(SUBS),
    "DELETE /api/admin/subscriptions/s1": () =>
      json({ detail: "not_found" }, 404),
  });
  render(<Subscriptions confirm={() => true} />);
  await screen.findByText("alpha");
  fireEvent.click(
    screen.getByRole("button", { name: "Delete subscription of alpha" }),
  );
  await vi.waitFor(() => expect(screen.queryByText("alpha")).toBeNull());
  expect(screen.queryByRole("alert")).toBeNull();
});

test("agent names and filter values are text, never markup", async () => {
  stub({
    "GET /api/admin/subscriptions": () =>
      json([
        {
          id: "s9",
          agent_id: "a9",
          agent_name: "<b>evil</b>",
          filter: { text: "<script>alert(1)</script>" },
          created_at: "2026-10-27T10:00:00Z",
        },
      ]),
  });
  const { container } = render(<Subscriptions />);
  await screen.findByText("<b>evil</b>");
  expect(screen.getByText("text: <script>alert(1)</script>")).toBeTruthy();
  expect(container.querySelector("b")).toBeNull();
  expect(container.querySelector("script")).toBeNull();
});

test("an empty list says so", async () => {
  stub({ "GET /api/admin/subscriptions": () => json([]) });
  render(<Subscriptions />);
  expect(
    (await screen.findByText(/no subscriptions/i)).textContent,
  ).toBeTruthy();
});

test("without permission the screen explains instead of listing", async () => {
  stub({
    "GET /api/admin/subscriptions": () => json({ detail: "forbidden" }, 403),
  });
  render(<Subscriptions />);
  expect((await screen.findByRole("alert")).textContent).toMatch(/permission/i);
});
