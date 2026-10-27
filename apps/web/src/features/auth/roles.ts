// Roles as the UI knows them (mirrors the API's permission table; the API is the
// authority and enforces every route, so this only decides which links to show).
export type Role = "owner" | "admin" | "viewer";

export function asRole(value: string): Role | null {
  return value === "owner" || value === "admin" || value === "viewer"
    ? value
    : null; // an unknown role unlocks nothing
}

export function canManageAgents(role: Role | null): boolean {
  return role === "owner" || role === "admin";
}

export function canManageUsers(role: Role | null): boolean {
  return role === "owner";
}
