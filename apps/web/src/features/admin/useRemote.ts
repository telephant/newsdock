"use client";
// Loads one list from the API for a management screen and lets the screen update it
// in place or reload it. A 401 is handled by the client (redirect to /login); a 403
// and a network failure become a message the screen shows instead of the list.
import { useCallback, useEffect, useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { apiRequest } from "@/lib/client/api";
import { adminMessage } from "./messages";

export type Remote<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string };

export function useRemote<T>(path: string) {
  const { apiBaseUrl } = useRuntimeConfig();
  const [remote, setRemote] = useState<Remote<T>>({ status: "loading" });

  const reload = useCallback(async () => {
    const result = await apiRequest<T>({ apiBaseUrl }, path);
    setRemote(
      result.kind === "ok"
        ? { status: "ready", data: result.data }
        : { status: "error", message: adminMessage(result) },
    );
  }, [apiBaseUrl, path]);

  useEffect(() => {
    // the state is set in the promise callback, not synchronously in the effect body
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload]);

  const update = useCallback((change: (data: T) => T) => {
    setRemote((current) =>
      current.status === "ready"
        ? { status: "ready", data: change(current.data) }
        : current,
    );
  }, []);

  return { remote, reload, update };
}
