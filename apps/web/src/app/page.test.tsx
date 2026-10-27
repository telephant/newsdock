import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Home from "./page";

vi.stubGlobal(
  "fetch",
  vi.fn(
    async () =>
      new Response(JSON.stringify({ articles: [], next_before: null })),
  ),
);

afterEach(cleanup);

test("home page shows its heading and the feed", () => {
  // the product name now lives in the app shell's wordmark, not in the page
  render(<Home />);
  expect(screen.getByRole("heading", { name: "Latest news" })).toBeTruthy();
  expect(screen.getByRole("form", { name: "filters" })).toBeTruthy();
});
