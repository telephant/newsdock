// TC-26: the feed renders articles; agent payload text is escaped, never HTML.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Feed } from "./Feed";
import type { FeedPage } from "./api";

const page: FeedPage = {
  articles: [
    {
      article_id: "aaa1",
      title: "Fed raises rates",
      url: "https://example.com/fed",
      domain: "example.com",
      published_at: "2026-10-05T10:00:00Z",
      themes: ["ECON_INFLATION"],
      scores: { "demo-financial": 0.91 },
      source_count: 3,
    },
    {
      article_id: "bbb2",
      title: "<script>alert('xss-title')</script>",
      url: "https://example.com/x",
      domain: "beta.org",
      published_at: "2026-10-05T09:00:00Z",
      themes: [],
      scores: null,
      source_count: 1,
    },
  ],
  next_before: null,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(page))),
  );
}

test("feed lists articles newest first with the agent score where present", async () => {
  stubFetch();
  render(<Feed />);
  const headings = await screen.findAllByRole("link", { name: /Fed|script/ });
  expect(headings[0].textContent).toContain("Fed raises rates");
  expect(screen.getByText("0.91")).toBeTruthy();
});

test("a grouped story shows the sites badge; single-source items do not", async () => {
  stubFetch();
  render(<Feed />);
  await screen.findByText(/Fed raises rates/);
  expect(screen.getByText("· 3 sites")).toBeTruthy(); // TC-11 (AC-10)
  expect(screen.queryByText("· 1 sites")).toBeNull();
});

test("payload-ish text renders escaped, never as HTML", async () => {
  stubFetch();
  const { container } = render(<Feed />);
  await screen.findByText(/xss-title/);
  expect(container.querySelector("script")).toBeNull(); // nothing injected
  expect(container.textContent).toContain(
    "<script>alert('xss-title')</script>",
  );
});
