// TC-6, TC-7 (AC-4): one feed card.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ArticleItem } from "./ArticleItem";
import type { ArticleSummary } from "./api";

afterEach(cleanup);

const base: ArticleSummary = {
  article_id: "aaa1",
  title: "Fed raises rates",
  url: "https://example.com/fed",
  domain: "example.com",
  published_at: "2026-10-05T10:00:00Z",
  themes: ["ECON_INFLATION"],
  scores: { "demo-financial": 0.91 },
  source_count: 3,
};

const show = (article: Partial<ArticleSummary> = {}) =>
  render(
    <ol>
      <ArticleItem article={{ ...base, ...article }} />
    </ol>,
  );

test("a card links the title, shows domain, time, sites and scores", () => {
  show();
  const link = screen.getByRole("link", { name: "Fed raises rates" });
  expect(link.getAttribute("href")).toBe("/articles/aaa1");
  expect(screen.getByText("example.com")).toBeTruthy();
  const time = document.querySelector("time");
  expect(time?.getAttribute("datetime")).toBe("2026-10-05T10:00:00Z");
  expect(time?.getAttribute("title")).toBeTruthy(); // the full local date
  expect(screen.getByText("3 sites")).toBeTruthy();
  const score = screen.getByText("0.91");
  expect(score.getAttribute("title")).toBe("demo-financial");
});

test("single-source stories have no sites badge; a missing domain reads unknown", () => {
  show({ source_count: 1, domain: null, scores: null });
  expect(screen.queryByText(/sites/)).toBeNull();
  expect(screen.getByText("unknown")).toBeTruthy();
});

test("long and CJK titles wrap and are clamped inside the card", () => {
  const long = "x".repeat(300);
  show({ title: long });
  const link = screen.getByRole("link", { name: long });
  expect(link.className).toContain("break-words");
  expect(link.className).toMatch(/line-clamp-\d/);
  cleanup();
  show({ title: "日本銀行は政策金利を据え置いた" });
  const cjk = screen.getByRole("link", { name: /日本銀行/ });
  expect(cjk.className).toContain("break-words");
  expect(cjk.closest("li")?.firstElementChild?.className).toContain("min-w-0");
});

test("the title is text, never markup", () => {
  show({ title: "<script>alert(1)</script>" });
  expect(document.querySelector("script")).toBeNull();
});
