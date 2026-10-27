// TC-4 (AC-3): the shell shows the wordmark (not a link), the role-aware links with
// the current page marked, the user area and the theme toggle.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ConfigProvider } from "@/components/ConfigProvider";
import { Nav } from "@/features/auth/Nav";
import { SessionProvider } from "@/features/auth/SessionProvider";
import { DEFAULT_CONFIG } from "@/lib/config/types";
import { AppShell } from "./AppShell";
import { ThemeProvider } from "./ThemeProvider";

vi.mock("next/navigation", () => ({ usePathname: () => "/admin/agents" }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function setup(role: string, notice?: string | null) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {}, // next-themes still uses the legacy pair
      removeListener: () => {},
    })),
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({ id: "u1", email: `${role}@x.io`, role }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        ),
    ),
  );
  render(
    <ThemeProvider>
      <ConfigProvider value={DEFAULT_CONFIG}>
        <SessionProvider
          deps={{
            navigate: vi.fn(),
            location: () => ({ pathname: "/admin/agents", search: "" }),
          }}
        >
          <AppShell nav={<Nav />} notice={notice}>
            <p>page body</p>
          </AppShell>
        </SessionProvider>
      </ConfigProvider>
    </ThemeProvider>,
  );
}

test("an admin sees the wordmark, role links, the user area and the toggle", async () => {
  setup("admin");
  await screen.findByText("admin@x.io");

  const wordmark = screen.getByText("newsdock");
  expect(wordmark.closest("a")).toBeNull(); // text, not a link

  const nav = screen.getByRole("navigation", { name: "main" });
  const links = within(nav).getAllByRole("link");
  expect(links.map((l) => l.textContent)).toEqual([
    "Feed",
    "Live",
    "Agents",
    "Subscriptions",
  ]);
  const current = links.filter(
    (l) => l.getAttribute("aria-current") === "page",
  );
  expect(current.map((l) => l.textContent)).toEqual(["Agents"]);

  expect(within(nav).getByText("admin")).toBeTruthy(); // role badge
  expect(screen.getByRole("button", { name: "Log out" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Toggle theme" })).toBeTruthy();
});

test("the page body sits in the main landmark behind a skip link", async () => {
  setup("viewer");
  await screen.findByText("viewer@x.io");
  const main = screen.getByRole("main");
  expect(main.id).toBe("content");
  expect(within(main).getByText("page body")).toBeTruthy();
  const skip = screen.getByRole("link", { name: "Skip to content" });
  expect(skip.getAttribute("href")).toBe("#content");
});

test("a host problem is shown as an alert above the page", async () => {
  setup("viewer", "Open the site on 127.0.0.1");
  await screen.findByText("viewer@x.io");
  expect((await screen.findByRole("alert")).textContent).toContain("127.0.0.1");
});
