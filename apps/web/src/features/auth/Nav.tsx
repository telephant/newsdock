"use client";
// Main navigation (AC-9). Links follow the role; hiding one is cosmetic, the API
// enforces every permission. Everything shown is a React text node (escaped).
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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
    <nav aria-label="main" className="flex min-w-0 items-center gap-2">
      {/* on a phone the links scroll sideways; the fade at the right edge says so */}
      <div className="flex min-w-0 items-center gap-1 overflow-x-auto max-sm:[mask-image:linear-gradient(to_right,black_calc(100%-1.5rem),transparent)]">
        <NavLink href="/">Feed</NavLink>
        <NavLink href="/live">Live</NavLink>
        {canManageAgents(role) ? (
          <>
            <NavLink href="/admin/agents">Agents</NavLink>
            <NavLink href="/admin/subscriptions">Subscriptions</NavLink>
          </>
        ) : null}
        {canManageUsers(role) ? (
          <NavLink href="/admin/users">Users</NavLink>
        ) : null}
      </div>
      {session.status === "user" ? (
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden text-sm text-muted-foreground sm:inline">
            {session.user.email}
          </span>
          <Badge variant="secondary" className="max-sm:hidden">
            {session.user.role}
          </Badge>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={logout}
            disabled={leaving}
          >
            Log out
          </Button>
        </div>
      ) : null}
      {session.status === "anonymous" && loginRequired ? (
        <div className="ml-auto flex items-center gap-1">
          <NavLink href="/login">Log in</NavLink>
          <NavLink href="/signup">Sign up</NavLink>
        </div>
      ) : null}
      {session.status === "unreachable" ? (
        <Alert role="status" className="ml-auto w-auto py-1">
          Cannot reach the server. Reload to try again.
        </Alert>
      ) : null}
    </nav>
  );
}

// A link styled as a ghost button; the current page is marked for assistive tech.
function NavLink({ href, children }: { href: string; children: string }) {
  const pathname = usePathname();
  const current =
    pathname !== null &&
    (href === "/" ? pathname === "/" : pathname.startsWith(href));
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={cn(
        buttonVariants({
          variant: current ? "secondary" : "ghost",
          size: "sm",
        }),
      )}
    >
      {children}
    </Link>
  );
}
