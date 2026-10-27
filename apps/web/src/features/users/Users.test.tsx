// TC-27 (AC-10): the owner's user screen. The API refuses the last-owner change; the
// screen shows that answer and puts the select back.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Users } from "./Users";

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

const USERS = [
  {
    id: "u1",
    email: "owner@x.io",
    role: "owner",
    created_at: "2026-10-27T10:00:00Z",
  },
  {
    id: "u2",
    email: "viewer@x.io",
    role: "viewer",
    created_at: "2026-10-27T11:00:00Z",
  },
];

const roleSelect = (email: string) =>
  screen.getByLabelText(`Role of ${email}`) as HTMLSelectElement;

test("lists every user with the role select and emails as plain text", async () => {
  stub({
    "GET /api/users": () =>
      json([
        ...USERS,
        {
          id: "u3",
          email: "<img src=x onerror=alert(1)>@x.io",
          role: "admin",
          created_at: "2026-10-27T12:00:00Z",
        },
      ]),
  });
  const { container } = render(<Users />);
  await screen.findByText("owner@x.io");
  expect(roleSelect("owner@x.io").value).toBe("owner");
  expect(roleSelect("viewer@x.io").value).toBe("viewer");
  expect(screen.getByText("<img src=x onerror=alert(1)>@x.io")).toBeTruthy();
  expect(container.querySelector("img")).toBeNull();
  expect(
    within(roleSelect("viewer@x.io"))
      .getAllByRole("option")
      .map((o) => o.textContent),
  ).toEqual(["owner", "admin", "viewer"]);
});

test("changing a role sends PATCH with the new role and keeps it", async () => {
  const fetchMock = stub({
    "GET /api/users": () => json(USERS),
    "PATCH /api/users/u2": () =>
      json({ id: "u2", email: "viewer@x.io", role: "admin" }),
  });
  render(<Users />);
  await screen.findByText("viewer@x.io");
  fireEvent.change(roleSelect("viewer@x.io"), { target: { value: "admin" } });
  await vi.waitFor(() => {
    const patch = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "PATCH",
    );
    expect(patch).toBeTruthy();
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ role: "admin" });
    expect(patch?.[1]?.credentials).toBe("include");
  });
  await vi.waitFor(() => expect(roleSelect("viewer@x.io").value).toBe("admin"));
  expect(screen.queryByRole("alert")).toBeNull();
});

test("the last owner cannot be demoted: the message shows and the select goes back", async () => {
  stub({
    "GET /api/users": () => json(USERS),
    "PATCH /api/users/u1": () => json({ detail: "last_owner" }, 409),
  });
  render(<Users />);
  await screen.findByText("owner@x.io");
  fireEvent.change(roleSelect("owner@x.io"), { target: { value: "viewer" } });
  expect((await screen.findByRole("alert")).textContent).toMatch(/last owner/i);
  expect(roleSelect("owner@x.io").value).toBe("owner");
});

test("deleting asks first; cancelling sends nothing", async () => {
  const fetchMock = stub({ "GET /api/users": () => json(USERS) });
  const confirm = vi.fn(() => false);
  render(<Users confirm={confirm} />);
  await screen.findByText("viewer@x.io");
  fireEvent.click(screen.getByRole("button", { name: "Delete viewer@x.io" }));
  expect(confirm).toHaveBeenCalledOnce();
  expect(String(confirm.mock.calls[0])).toContain("viewer@x.io");
  expect(
    fetchMock.mock.calls.filter(([, i]) => i?.method === "DELETE"),
  ).toHaveLength(0);
  expect(screen.getByText("viewer@x.io")).toBeTruthy();
});

test("a confirmed delete removes the row", async () => {
  const fetchMock = stub({
    "GET /api/users": () => json(USERS),
    "DELETE /api/users/u2": () => new Response(null, { status: 204 }),
  });
  render(<Users confirm={() => true} />);
  await screen.findByText("viewer@x.io");
  fireEvent.click(screen.getByRole("button", { name: "Delete viewer@x.io" }));
  await vi.waitFor(() => expect(screen.queryByText("viewer@x.io")).toBeNull());
  expect(screen.getByText("owner@x.io")).toBeTruthy();
  expect(fetchMock.mock.calls.some(([, i]) => i?.method === "DELETE")).toBe(
    true,
  );
});

test("deleting the last owner is refused and the row stays", async () => {
  stub({
    "GET /api/users": () => json(USERS),
    "DELETE /api/users/u1": () => json({ detail: "last_owner" }, 409),
  });
  render(<Users confirm={() => true} />);
  await screen.findByText("owner@x.io");
  fireEvent.click(screen.getByRole("button", { name: "Delete owner@x.io" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/last owner/i);
  expect(screen.getByText("owner@x.io")).toBeTruthy();
});

test("someone without the permission sees a clear message instead of a table", async () => {
  stub({ "GET /api/users": () => json({ detail: "forbidden" }, 403) });
  render(<Users />);
  expect((await screen.findByRole("alert")).textContent).toMatch(/permission/i);
  expect(screen.queryByRole("table")).toBeNull();
});

test("an unreachable server is reported", async () => {
  vi.stubGlobal("fetch", async () => {
    throw new TypeError("Failed to fetch");
  });
  render(<Users />);
  expect((await screen.findByRole("alert")).textContent).toMatch(
    /cannot reach/i,
  );
});
