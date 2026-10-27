// Relative times for the feed cards; the full date stays in the title attribute.
import { expect, test } from "vitest";
import { timeAgo } from "./time";

const now = Date.parse("2026-10-27T12:00:00Z");

test.each([
  ["2026-10-27T11:59:40Z", "just now"],
  ["2026-10-27T11:55:00Z", "5 minutes ago"],
  ["2026-10-27T09:00:00Z", "3 hours ago"],
  ["2026-10-25T12:00:00Z", "2 days ago"],
])("%s reads %s", (iso, text) => {
  expect(timeAgo(iso, now)).toBe(text);
});

test("older than a week falls back to a short date", () => {
  expect(timeAgo("2026-10-01T12:00:00Z", now)).toMatch(/Oct/);
});

test("a time slightly in the future (clock skew) reads just now", () => {
  expect(timeAgo("2026-10-27T12:00:30Z", now)).toBe("just now");
});

test("an unparseable value is returned unchanged", () => {
  expect(timeAgo("not a date", now)).toBe("not a date");
});
