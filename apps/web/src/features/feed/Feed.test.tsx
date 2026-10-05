// TC-26: the feed renders articles; agent payload text is escaped, never HTML.
import { render, screen } from "@testing-library/react";
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
    },
    {
      article_id: "bbb2",
      title: "<script>alert('xss-title')</script>",
      url: "https://example.com/x",
      domain: "beta.org",
      published_at: "2026-10-05T09:00:00Z",
      themes: [],
      scores: null,
    },
  ],
  next_before: null,
};

afterEach(() => vi.unstubAllGlobals());

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

test("payload-ish text renders escaped, never as HTML", async () => {
  stubFetch();
  const { container } = render(<Feed />);
  await screen.findByText(/xss-title/);
  expect(container.querySelector("script")).toBeNull(); // nothing injected
  expect(container.textContent).toContain(
    "<script>alert('xss-title')</script>",
  );
});
