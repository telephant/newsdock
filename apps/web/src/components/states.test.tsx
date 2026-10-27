// TC-19 (AC-13): shared page header and loading / empty / error states.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { EmptyState } from "./EmptyState";
import { ErrorAlert } from "./ErrorAlert";
import { ListSkeleton } from "./ListSkeleton";
import { PageHeader } from "./PageHeader";

afterEach(cleanup);

test("the page header has one h1, an optional description and actions", () => {
  render(
    <PageHeader
      title="Latest news"
      description="Newest first"
      actions={<button>Do it</button>}
    />,
  );
  expect(
    screen.getByRole("heading", { level: 1, name: "Latest news" }),
  ).toBeTruthy();
  expect(screen.getByText("Newest first")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Do it" })).toBeTruthy();
});

test("the skeleton list is busy, hidden from the tree and says it is loading", () => {
  const { container } = render(<ListSkeleton rows={3} />);
  expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBe(
    3 * 3,
  ); // three lines per row
  expect(container.firstElementChild?.getAttribute("aria-busy")).toBe("true");
  expect(screen.getByText("Loading…")).toBeTruthy();
});

test("the empty state shows its title and hint as text", () => {
  render(<EmptyState title="No articles" description="Try other filters" />);
  expect(screen.getByText("No articles")).toBeTruthy();
  expect(screen.getByText("Try other filters")).toBeTruthy();
});

test("the error alert uses role=alert and renders the message as text", () => {
  const { container } = render(<ErrorAlert message="<b>boom</b>" />);
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toContain("<b>boom</b>");
  expect(container.querySelector("b")).toBeNull();
});
