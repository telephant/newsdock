// TC-14 (code part of AC-9): the toggle flips the `dark` class on <html> and the
// choice is remembered. The flash-free first paint is checked by hand (M-1).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ThemeProvider } from "./ThemeProvider";
import { ThemeToggle } from "./ThemeToggle";

beforeEach(() => {
  // jsdom has no matchMedia; the system prefers light
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
    })),
  );
  localStorage.clear();
  document.documentElement.className = "";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function setup() {
  render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  );
  return screen.getByRole("button", { name: "Toggle theme" });
}

test("the toggle switches the dark class and remembers the choice", () => {
  const toggle = setup();
  expect(document.documentElement.classList.contains("dark")).toBe(false);

  fireEvent.click(toggle);
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  expect(localStorage.getItem("theme")).toBe("dark");

  fireEvent.click(toggle);
  expect(document.documentElement.classList.contains("dark")).toBe(false);
  expect(localStorage.getItem("theme")).toBe("light");
});

test("a stored dark choice is applied on load", () => {
  localStorage.setItem("theme", "dark");
  setup();
  expect(document.documentElement.classList.contains("dark")).toBe(true);
});

test("blocked storage does not break the toggle", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  const toggle = setup();
  fireEvent.click(toggle);
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  vi.restoreAllMocks();
});
