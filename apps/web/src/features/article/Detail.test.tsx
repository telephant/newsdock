// TC-11 (AC-10): the detail lists sources as escaped text/links.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Detail } from "./Detail";
import type { ArticleDetail } from "../feed/api";

const detail: ArticleDetail = {
  article_id: "aaa1",
  title: "Fed raises rates",
  url: "https://example.com/fed",
  domain: "example.com",
  published_at: "2026-10-05T10:00:00Z",
  ingested_at: "2026-10-05T10:05:00Z",
  slot: "20261005100000",
  themes: ["ECON_INFLATION"],
  persons: [],
  orgs: [],
  tone: 1.2,
  word_count: 300,
  analyses: [],
  source_count: 2,
  sources: [
    {
      url: "https://example.com/fed",
      domain: "example.com",
      published_at: "2026-10-05T10:00:00Z",
    },
    {
      url: "https://other.example/<script>alert('xss-src')</script>",
      domain: "other.example",
      published_at: "2026-10-05T11:00:00Z",
    },
  ],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("detail shows the sources section with escaped urls", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(detail))),
  );
  const { container } = render(<Detail articleId="aaa1" />);
  await screen.findByText(/Seen on 2 sites/);
  expect(screen.getByText("other.example")).toBeTruthy();
  expect(container.querySelector("script")).toBeNull(); // nothing injected
  expect(container.textContent).toContain("<script>alert('xss-src')</script>");
});
