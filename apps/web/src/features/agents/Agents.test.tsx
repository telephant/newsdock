// TC-28 (AC-11): agents and keys. A key secret exists only in component state, is
// shown once with a copy button, and is gone on dismiss, on a new key and on leaving.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConfigProvider } from "@/components/ConfigProvider";
import { DEFAULT_CONFIG } from "@/lib/config/types";
import { SessionProvider } from "../auth/SessionProvider";
import { Agents } from "./Agents";

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

const KEY = "ndk_ab12cd34_thisisthesecretpartofthekey";

const key = (over: object = {}) => ({
  key_id: "k1",
  prefix: "ab12cd34",
  created_at: "2026-10-27T10:00:00Z",
  revoked_at: null,
  last_used_at: null,
  ...over,
});

const agent = (over: object = {}) => ({
  agent_id: "a1",
  name: "alpha",
  status: "active",
  keys: [key()],
  ...over,
});

const calls = (fetchMock: ReturnType<typeof stub>, method: string) =>
  fetchMock.mock.calls.filter(([, init]) => init?.method === method);

test("lists agents with status and key prefixes, and never a secret", async () => {
  stub({
    "GET /api/admin/agents": () =>
      json([
        agent(),
        agent({
          agent_id: "a2",
          name: "beta",
          status: "disabled",
          keys: [
            key({
              key_id: "k2",
              prefix: "ff00ee11",
              revoked_at: "2026-10-27T11:00:00Z",
            }),
          ],
        }),
      ]),
  });
  const { container } = render(<Agents />);
  await screen.findByText("alpha");
  expect(screen.getByText("beta")).toBeTruthy();
  expect(screen.getByText("ab12cd34")).toBeTruthy();
  expect(screen.getByText(/revoked/i)).toBeTruthy();
  expect(container.textContent).not.toContain("ndk_");
});

test("a hostile agent name is shown as text", async () => {
  stub({
    "GET /api/admin/agents": () =>
      json([agent({ name: "<img src=x onerror=alert(1)>" })]),
  });
  const { container } = render(<Agents />);
  await screen.findByText("<img src=x onerror=alert(1)>");
  expect(container.querySelector("img")).toBeNull();
});

test("creating an agent shows its key once, with a copy button and a warning", async () => {
  let agents = [agent()];
  const fetchMock = stub({
    "GET /api/admin/agents": () => json(agents),
    "POST /api/admin/agents": () => {
      agents = [
        ...agents,
        agent({
          agent_id: "a2",
          name: "gamma",
          keys: [key({ key_id: "k9", prefix: "99887766" })],
        }),
      ];
      return json(
        { agent_id: "a2", name: "gamma", key_id: "k9", api_key: KEY },
        201,
      );
    },
  });
  const copy = vi.fn(async () => {});
  render(<Agents copy={copy} />);
  await screen.findByText("alpha");
  fireEvent.change(screen.getByLabelText("Agent name"), {
    target: { value: "gamma" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create agent" }));

  const panel = await screen.findByRole("status");
  expect(within(panel).getByText(KEY)).toBeTruthy();
  expect(panel.textContent).toMatch(/only once/i);
  expect(panel.textContent).toContain("gamma");
  expect(JSON.parse(String(calls(fetchMock, "POST")[0][1]?.body))).toEqual({
    name: "gamma",
  });

  fireEvent.click(within(panel).getByRole("button", { name: "Copy key" }));
  expect(copy).toHaveBeenCalledWith(KEY);

  await screen.findByText("gamma"); // the list was reloaded...
  expect(screen.getAllByText(KEY)).toHaveLength(1); // ...and still lists no secret
  expect((screen.getByLabelText("Agent name") as HTMLInputElement).value).toBe(
    "",
  );
});

test("dismissing the panel, or leaving the page, drops the key", async () => {
  stub({
    "GET /api/admin/agents": () => json([agent()]),
    "POST /api/admin/agents": () =>
      json({ agent_id: "a2", name: "gamma", key_id: "k9", api_key: KEY }, 201),
  });
  const first = render(<Agents />);
  await screen.findByText("alpha");
  fireEvent.change(screen.getByLabelText("Agent name"), {
    target: { value: "gamma" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create agent" }));
  await screen.findByText(KEY);
  fireEvent.click(screen.getByRole("button", { name: "I have copied it" }));
  expect(screen.queryByText(KEY)).toBeNull();

  fireEvent.change(screen.getByLabelText("Agent name"), {
    target: { value: "gamma" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create agent" }));
  await screen.findByText(KEY);
  first.unmount(); // navigating away
  render(<Agents />);
  await screen.findByText("alpha");
  expect(screen.queryByText(KEY)).toBeNull();
  expect(document.body.textContent).not.toContain(KEY);
});

test("a new key replaces the previous one on screen", async () => {
  const second = "ndk_ee00ee00_anothersecretkeyvalue";
  const keys = [KEY, second];
  stub({
    "GET /api/admin/agents": () => json([agent()]),
    "POST /api/admin/agents/a1/keys": () =>
      json({ key_id: "k5", api_key: keys.shift() }, 201),
  });
  render(<Agents />);
  await screen.findByText("alpha");
  fireEvent.click(screen.getByRole("button", { name: "New key for alpha" }));
  await screen.findByText(KEY);
  fireEvent.click(screen.getByRole("button", { name: "New key for alpha" }));
  await screen.findByText(second);
  expect(screen.queryByText(KEY)).toBeNull();
});

test("name problems are explained", async () => {
  stub({
    "GET /api/admin/agents": () => json([agent()]),
    "POST /api/admin/agents": (init) => {
      const name = JSON.parse(String(init?.body)).name;
      return name === "alpha"
        ? json({ detail: "name_taken" }, 409)
        : json({ detail: [{ msg: "String should match pattern" }] }, 422);
    },
  });
  render(<Agents />);
  await screen.findByText("alpha");
  fireEvent.change(screen.getByLabelText("Agent name"), {
    target: { value: "alpha" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create agent" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(
    /already exists/i,
  );
  fireEvent.change(screen.getByLabelText("Agent name"), {
    target: { value: "Bad Name!" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create agent" }));
  await vi.waitFor(() =>
    expect(screen.getByRole("alert").textContent).toMatch(
      /lowercase letters, digits/i,
    ),
  );
  expect(screen.queryByRole("status")).toBeNull(); // no key was shown
});

test("revoking a key asks first, then calls the right route and reloads", async () => {
  let agents = [agent()];
  const fetchMock = stub({
    "GET /api/admin/agents": () => json(agents),
    "DELETE /api/admin/agents/a1/keys/k1": () => {
      agents = [agent({ keys: [key({ revoked_at: "2026-10-27T12:00:00Z" })] })];
      return new Response(null, { status: 204 });
    },
  });
  const confirm = vi.fn(() => false);
  const { rerender } = render(<Agents confirm={confirm} />);
  await screen.findByText("alpha");
  fireEvent.click(screen.getByRole("button", { name: "Revoke key ab12cd34" }));
  expect(confirm).toHaveBeenCalledOnce();
  expect(calls(fetchMock, "DELETE")).toHaveLength(0);

  rerender(<Agents confirm={() => true} />);
  fireEvent.click(screen.getByRole("button", { name: "Revoke key ab12cd34" }));
  await vi.waitFor(() => expect(calls(fetchMock, "DELETE")).toHaveLength(1));
  await screen.findByText(/revoked/i);
  expect(
    screen.queryByRole("button", { name: "Revoke key ab12cd34" }),
  ).toBeNull();
});

test("an agent can be disabled and enabled again", async () => {
  let status = "active";
  const fetchMock = stub({
    "GET /api/admin/agents": () => json([agent({ status })]),
    "POST /api/admin/agents/a1/disable": () => {
      status = "disabled";
      return new Response(null, { status: 204 });
    },
    "POST /api/admin/agents/a1/enable": () => {
      status = "active";
      return new Response(null, { status: 204 });
    },
  });
  render(<Agents />);
  fireEvent.click(await screen.findByRole("button", { name: "Disable alpha" }));
  fireEvent.click(await screen.findByRole("button", { name: "Enable alpha" }));
  await screen.findByRole("button", { name: "Disable alpha" });
  expect(
    calls(fetchMock, "POST").map(([url]) => new URL(url).pathname),
  ).toEqual(["/api/admin/agents/a1/disable", "/api/admin/agents/a1/enable"]);
});

test("a viewer sees a permission message, not the screen", async () => {
  stub({ "GET /api/admin/agents": () => json({ detail: "forbidden" }, 403) });
  render(<Agents />);
  expect((await screen.findByRole("alert")).textContent).toMatch(/permission/i);
  expect(screen.queryByLabelText("Agent name")).toBeNull();
});

// TC-10, TC-11, TC-19 (AC-7, AC-13): keys in a table, status badges, dialog, loading.
test("each agent shows a status badge and its keys in a table", async () => {
  stub({
    "GET /api/admin/agents": () =>
      json([
        agent(),
        agent({
          agent_id: "a2",
          name: "beta",
          status: "disabled",
          keys: [
            key({
              key_id: "k2",
              prefix: "ff00ee11",
              revoked_at: "2026-10-27T11:00:00Z",
            }),
          ],
        }),
      ]),
  });
  render(<Agents />);
  await screen.findByText("alpha");
  expect(screen.getByText("active").getAttribute("data-slot")).toBe("badge");
  expect(screen.getByText("disabled").getAttribute("data-slot")).toBe("badge");
  const tables = screen.getAllByRole("table");
  expect(tables).toHaveLength(2); // one key table per agent
  expect(
    within(tables[0])
      .getAllByRole("columnheader")
      .map((h) => h.textContent),
  ).toEqual(["Key", "Created", "Last used", "Status", ""]);
  expect(screen.getByText(/revoked/i).getAttribute("data-slot")).toBe("badge");
});

test("while loading a skeleton is shown", () => {
  stub({
    "GET /api/admin/agents": () => new Promise<Response>(() => {}) as never,
  });
  const { container } = render(<Agents />);
  expect(container.querySelector('[data-slot="skeleton"]')).not.toBeNull();
});

test("an empty registry shows an empty state next to the create form", async () => {
  stub({ "GET /api/admin/agents": () => json([]) });
  render(<Agents />);
  expect(await screen.findByText("You have no agents yet.")).toBeTruthy();
  expect(screen.getByLabelText("Agent name")).toBeTruthy();
});

// TC-15 (AC-11): the owner role also sees whose each agent is; everyone else, who
// only ever receives their own agents, gets no creator line
function renderAs(role: string, agents: object[]) {
  stub({
    "GET /api/auth/me": () =>
      json({ id: "u1", email: `${role}@x.io`, role }, 200),
    "GET /api/admin/agents": () => json(agents),
  });
  return render(
    <ConfigProvider value={DEFAULT_CONFIG}>
      <SessionProvider>
        <Agents />
      </SessionProvider>
    </ConfigProvider>,
  );
}

test("a viewer sees the returned agents and no creator", async () => {
  renderAs("viewer", [agent({ owner_id: "u1", owner_email: "viewer@x.io" })]);
  expect(await screen.findByText("alpha")).toBeTruthy();
  expect(screen.queryByText(/created by/i)).toBeNull();
});

test("the owner role sees the creator, or 'no owner' for an unowned agent", async () => {
  renderAs("owner", [
    agent({ owner_id: "u2", owner_email: "ann@x.io" }),
    agent({
      agent_id: "a2",
      name: "legacy",
      owner_id: null,
      owner_email: null,
    }),
  ]);
  expect(await screen.findByText("ann@x.io")).toBeTruthy();
  expect(screen.getByText("no owner")).toBeTruthy();
});

test("the default revoke confirmation is a dialog", async () => {
  let agents = [agent()];
  const fetchMock = stub({
    "GET /api/admin/agents": () => json(agents),
    "DELETE /api/admin/agents/a1/keys/k1": () => {
      agents = [agent({ keys: [key({ revoked_at: "2026-10-27T12:00:00Z" })] })];
      return new Response(null, { status: 204 });
    },
  });
  render(<Agents />);
  await screen.findByText("alpha");
  fireEvent.click(screen.getByRole("button", { name: "Revoke key ab12cd34" }));
  const dialog = await screen.findByRole("alertdialog");
  expect(dialog.textContent).toContain("ab12cd34");
  expect(calls(fetchMock, "DELETE")).toHaveLength(0);
  fireEvent.click(within(dialog).getByRole("button", { name: "Revoke" }));
  await vi.waitFor(() => expect(calls(fetchMock, "DELETE")).toHaveLength(1));
  await screen.findByText(/revoked/i);
});
