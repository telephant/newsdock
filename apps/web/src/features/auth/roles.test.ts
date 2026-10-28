// TC-16 (AC-11): every known role may manage its own agents; only the owner role
// manages users. The API enforces both; this only decides which links to show.
import { expect, test } from "vitest";
import { asRole, canManageAgents, canManageUsers } from "./roles";

test("every known role can manage agents, an unknown or missing one cannot", () => {
  expect(canManageAgents("owner")).toBe(true);
  expect(canManageAgents("admin")).toBe(true);
  expect(canManageAgents("viewer")).toBe(true);
  expect(canManageAgents(null)).toBe(false);
  expect(canManageAgents(asRole("superuser"))).toBe(false);
});

test("only the owner role manages users", () => {
  expect(canManageUsers("owner")).toBe(true);
  expect(canManageUsers("admin")).toBe(false);
  expect(canManageUsers("viewer")).toBe(false);
  expect(canManageUsers(null)).toBe(false);
});
