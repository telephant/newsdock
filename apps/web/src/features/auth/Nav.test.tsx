// TC-25 (AC-9): the navigation follows the role, and a lost session goes to /login.
// Hiding a link is cosmetic: the API enforces every permission.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConfigProvider } from "@/components/ConfigProvider";
import { DEFAULT_CONFIG } from "@/lib/config/types";
import { Nav } from "./Nav";
import { SessionProvider } from "./SessionProvider";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

function setup(
  respond: (url: string, init?: RequestInit) => Response | Promise<Response>,
  loginRequired = true,
) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) =>
    respond(url, init),
  );
  vi.stubGlobal("fetch", fetchMock);
  const navigate = vi.fn();
  render(
    <ConfigProvider value={{ ...DEFAULT_CONFIG, loginRequired }}>
      <SessionProvider
        deps={{ navigate, location: () => ({ pathname: "/live", search: "" }) }}
      >
        <Nav />
      </SessionProvider>
    </ConfigProvider>,
  );
  return { fetchMock, navigate };
}

const me = (role: string) =>
  json({ id: "u1", email: `${role}@x.io`, role }, 200);

const names = () => screen.getAllByRole("link").map((link) => link.textContent);

test("a viewer sees the feed, the live page and their own agents and subscriptions", async () => {
  setup(() => me("viewer"));
  await screen.findByText("viewer@x.io");
  expect(names()).toEqual(["Feed", "Live", "Agents", "Subscriptions"]);
});

test("an admin also sees agents and subscriptions", async () => {
  setup(() => me("admin"));
  await screen.findByText("admin@x.io");
  expect(names()).toEqual(["Feed", "Live", "Agents", "Subscriptions"]);
});

test("an owner also sees users", async () => {
  setup(() => me("owner"));
  await screen.findByText("owner@x.io");
  expect(names()).toEqual(["Feed", "Live", "Agents", "Subscriptions", "Users"]);
  const hrefs = screen.getAllByRole("link").map((l) => l.getAttribute("href"));
  expect(hrefs).toEqual([
    "/",
    "/live",
    "/admin/agents",
    "/admin/subscriptions",
    "/admin/users",
  ]);
});

test("while the session is loading no administrative link is shown", () => {
  setup(() => new Promise<Response>(() => {})); // never answers
  expect(names()).toEqual(["Feed", "Live"]);
  expect(screen.queryByText("Log out")).toBeNull();
});

test("an unknown role never unlocks anything", async () => {
  setup(() => me("superuser"));
  await screen.findByText("superuser@x.io");
  expect(names()).toEqual(["Feed", "Live"]);
});

test("a lost session (401) sends the user to /login and shows the sign-in links", async () => {
  const { navigate } = setup(() => json({ detail: "unauthorized" }, 401));
  await vi.waitFor(() =>
    expect(navigate).toHaveBeenCalledWith("/login?next=%2Flive"),
  );
  await screen.findByRole("link", { name: "Log in" });
  expect(screen.getByRole("link", { name: "Sign up" })).toBeTruthy();
  expect(names()).not.toContain("Agents");
});

test("in dev mode (login not required) a 401 is normal: no redirect, no sign-in links", async () => {
  const { navigate, fetchMock } = setup(
    () => json({ detail: "unauthorized" }, 401),
    false,
  );
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
  await vi.waitFor(() => expect(screen.queryByText("Log in")).toBeNull());
  expect(navigate).not.toHaveBeenCalled();
  expect(names()).toEqual(["Feed", "Live"]);
});

test("an unreachable server shows a notice instead of redirecting", async () => {
  const { navigate } = setup(() => {
    throw new TypeError("Failed to fetch");
  });
  expect((await screen.findByRole("status")).textContent).toMatch(
    /cannot reach/i,
  );
  expect(navigate).not.toHaveBeenCalled();
});

test("the email is shown as text, so markup in it is inert", async () => {
  setup(() => json({ id: "u", email: "<i>x</i>@x.io", role: "viewer" }));
  const shown = await screen.findByText("<i>x</i>@x.io");
  expect(shown.querySelector("i")).toBeNull();
});

test("logging out posts to the API and goes to the login page", async () => {
  const { fetchMock, navigate } = setup((url) =>
    url.endsWith("/api/auth/logout")
      ? new Response(null, { status: 204 })
      : me("viewer"),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Log out" }));
  await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith("/login"));
  const logout = fetchMock.mock.calls.find(([url]) =>
    String(url).endsWith("/api/auth/logout"),
  );
  expect(logout?.[1]?.method).toBe("POST");
  expect(logout?.[1]?.credentials).toBe("include");
});
