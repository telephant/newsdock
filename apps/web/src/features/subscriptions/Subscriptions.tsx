"use client";
// Subscriptions (AC-12, admin and owner): every agent's saved filters, with delete.
// Agents own and create their subscriptions; this screen only shows and removes them.
// All text is escaped by React.
import { useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import type { components } from "@/lib/api/types";
import { apiRequest } from "@/lib/client/api";
import { adminMessage, formatTime } from "../admin/messages";
import { useRemote } from "../admin/useRemote";

type AdminSubscription = components["schemas"]["AdminSubscription"];

export function Subscriptions({
  confirm = (message) => window.confirm(message),
}: {
  confirm?: (message: string) => boolean;
}) {
  const { apiBaseUrl } = useRuntimeConfig();
  const { remote, update } = useRemote<AdminSubscription[]>(
    "/api/admin/subscriptions",
  );
  const [notice, setNotice] = useState<string | null>(null);

  async function remove(sub: AdminSubscription) {
    if (
      !confirm(
        `Delete the subscription of ${sub.agent_name}? Its open stream ends shortly.`,
      )
    )
      return;
    setNotice(null);
    const result = await apiRequest(
      { apiBaseUrl },
      `/api/admin/subscriptions/${sub.id}`,
      { method: "DELETE" },
    );
    // a 404 means somebody else already removed it: the row should go either way
    if (
      result.kind === "ok" ||
      (result.kind === "error" && result.status === 404)
    ) {
      update((subs) => subs.filter((s) => s.id !== sub.id));
      return;
    }
    setNotice(adminMessage(result));
  }

  if (remote.status === "loading") return <p>Loading…</p>;
  if (remote.status === "error") return <p role="alert">{remote.message}</p>;
  if (remote.data.length === 0 && !notice) return <p>No subscriptions yet.</p>;

  return (
    <section>
      {notice ? <p role="alert">{notice}</p> : null}
      <ul>
        {remote.data.map((sub) => {
          const fields = Object.entries(sub.filter);
          return (
            <li key={sub.id}>
              <strong>{sub.agent_name}</strong>{" "}
              <small>created {formatTime(sub.created_at)}</small>
              <ul>
                {fields.length === 0 ? (
                  <li>any article (no filter)</li>
                ) : (
                  fields.map(([key, value]) => (
                    <li key={key}>{`${key}: ${String(value)}`}</li>
                  ))
                )}
              </ul>
              <button
                type="button"
                aria-label={`Delete subscription of ${sub.agent_name}`}
                onClick={() => void remove(sub)}
              >
                Delete
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
