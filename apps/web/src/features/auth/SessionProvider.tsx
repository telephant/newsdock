"use client";
// Who is signed in: asks GET /api/auth/me once per page load (a login or logout is a
// full page navigation, so the state is always fresh). The API is the authority; this
// only drives what the navigation shows. A 401 here sends the visitor to /login via
// the client, unless login is not required (dev mode: the API is open).
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import type { components } from "@/lib/api/types";
import { apiRequest, type ClientDeps } from "@/lib/client/api";

export type SessionUser = components["schemas"]["PublicUser"];

export type SessionState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "unreachable" }
  | { status: "user"; user: SessionUser };

type SessionContextValue = {
  state: SessionState;
  deps: ClientDeps | undefined;
};

const SessionContext = createContext<SessionContextValue>({
  state: { status: "loading" },
  deps: undefined,
});

export function SessionProvider({
  children,
  deps,
}: {
  children: ReactNode;
  deps?: ClientDeps; // test seam: fetch, navigate, location
}) {
  const { apiBaseUrl, loginRequired } = useRuntimeConfig();
  const [state, setState] = useState<SessionState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    // without required login a 401 is just "nobody", not a reason to leave the page
    const clientDeps: ClientDeps | undefined = loginRequired
      ? deps
      : { ...deps, navigate: () => {} };
    void apiRequest<SessionUser>(
      { apiBaseUrl },
      "/api/auth/me",
      undefined,
      clientDeps,
    ).then((result) => {
      if (cancelled) return;
      if (result.kind === "ok") setState({ status: "user", user: result.data });
      else if (result.kind === "unreachable" || result.status >= 500)
        setState({ status: "unreachable" });
      else setState({ status: "anonymous" });
    });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, loginRequired, deps]);

  return (
    <SessionContext.Provider value={{ state, deps }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  return useContext(SessionContext).state;
}

export function useSessionDeps(): ClientDeps | undefined {
  return useContext(SessionContext).deps;
}
