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

const respond = (body: unknown, status = 200) =>
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );

// TC-8 (AC-5): analysis payloads are escaped text in a card, never HTML.
test("an agent payload with markup stays text inside a preformatted block", async () => {
  respond({
    ...detail,
    analyses: [
      {
        agent_name: "demo-financial",
        payload: {
          relevant: true,
          score: 0.9,
          reason: "<img src=x onerror=alert(1)>",
        },
        created_at: "2026-10-05T12:00:00Z",
      },
    ],
  });
  const { container } = render(<Detail articleId="aaa1" />);
  await screen.findByText("demo-financial");
  expect(container.querySelector("img")).toBeNull();
  const pre = container.querySelector("pre");
  expect(pre?.textContent).toContain("<img src=x onerror=alert(1)>");
  expect(pre?.textContent).toContain('"score": 0.9'); // pretty-printed JSON
});

test("fields are laid out with a back link, themes as badges and the tone", async () => {
  respond(detail);
  render(<Detail articleId="aaa1" />);
  await screen.findByRole("heading", { level: 1, name: "Fed raises rates" });
  expect(
    screen.getByRole("link", { name: /Back to feed/ }).getAttribute("href"),
  ).toBe("/");
  expect(screen.getByText("ECON_INFLATION")).toBeTruthy();
  expect(screen.getByText("1.2")).toBeTruthy();
  expect(screen.getByText("None yet.")).toBeTruthy();
});

// TC-19 (AC-13), detail part: loading and failure use the shared components.
test("while loading a skeleton is shown", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );
  const { container } = render(<Detail articleId="aaa1" />);
  expect(container.querySelector('[data-slot="skeleton"]')).not.toBeNull();
});

test("a missing article shows an alert", async () => {
  respond({ detail: "not found" }, 404);
  render(<Detail articleId="nope" />);
  expect((await screen.findByRole("alert")).textContent).toMatch(/404/);
});
