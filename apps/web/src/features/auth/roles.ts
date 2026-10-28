// Roles as the UI knows them (mirrors the API's permission table; the API is the
// authority and enforces every route, so this only decides which links to show).
export type Role = "owner" | "admin" | "viewer";

export function asRole(value: string): Role | null {
  return value === "owner" || value === "admin" || value === "viewer"
    ? value
    : null; // an unknown role unlocks nothing
}

// Every signed-in user manages their own agents and subscriptions; the API limits
// each list to what the caller may see (the owner role sees all, ADR-0023).
export function canManageAgents(role: Role | null): boolean {
  return role !== null;
}

export function canManageUsers(role: Role | null): boolean {
  return role === "owner";
}
