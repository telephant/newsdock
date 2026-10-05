import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import Home from "./page";

vi.stubGlobal(
  "fetch",
  vi.fn(
    async () =>
      new Response(JSON.stringify({ articles: [], next_before: null })),
  ),
);

test("home page shows the product name and the feed", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { name: "newsdock" })).toBeTruthy();
  expect(screen.getByRole("form", { name: "filters" })).toBeTruthy();
});
