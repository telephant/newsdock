"use client";
// Main navigation (AC-9). Links follow the role; hiding one is cosmetic, the API
// enforces every permission. Everything shown is a React text node (escaped).
import Link from "next/link";
import { useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { apiRequest } from "@/lib/client/api";
import { asRole, canManageAgents, canManageUsers } from "./roles";
import { useSession, useSessionDeps } from "./SessionProvider";

export function Nav() {
  const session = useSession();
  const deps = useSessionDeps();
  const { apiBaseUrl, loginRequired } = useRuntimeConfig();
  const [leaving, setLeaving] = useState(false);

  const role = session.status === "user" ? asRole(session.user.role) : null;

  async function logout() {
    setLeaving(true);
    await apiRequest(
      { apiBaseUrl },
      "/api/auth/logout",
      { method: "POST" },
      deps,
    );
    // also when the cookie was already gone (401): the visitor is signed out either way
    (deps?.navigate ?? ((url: string) => window.location.assign(url)))(
      "/login",
    );
  }

  return (
    <nav aria-label="main">
      <Link href="/">Feed</Link> <Link href="/live">Live</Link>
      {canManageAgents(role) ? (
        <>
          {" "}
          <Link href="/admin/agents">Agents</Link>{" "}
          <Link href="/admin/subscriptions">Subscriptions</Link>
        </>
      ) : null}
      {canManageUsers(role) ? (
        <>
          {" "}
          <Link href="/admin/users">Users</Link>
        </>
      ) : null}
      {session.status === "user" ? (
        <span>
          {" "}
          <span>{session.user.email}</span> <small>{session.user.role}</small>{" "}
          <button type="button" onClick={logout} disabled={leaving}>
            Log out
          </button>
        </span>
      ) : null}
      {session.status === "anonymous" && loginRequired ? (
        <span>
          {" "}
          <Link href="/login">Log in</Link> <Link href="/signup">Sign up</Link>
        </span>
      ) : null}
      {session.status === "unreachable" ? (
        <p role="status">Cannot reach the server. Reload to try again.</p>
      ) : null}
    </nav>
  );
}
