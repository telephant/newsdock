"use client";
// Users (AC-10, owner only): change roles and delete accounts. The API enforces the
// permission and the "last owner stays" rule; this screen shows its answers and keeps
// the select in line with what the server accepted. All text is escaped by React.
import { useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import type { components } from "@/lib/api/types";
import { apiRequest } from "@/lib/client/api";
import { formatTime, userActionMessage } from "../admin/messages";
import { useRemote } from "../admin/useRemote";

type UserSummary = components["schemas"]["UserSummary"];
const ROLES = ["owner", "admin", "viewer"] as const;

export function Users({
  confirm = (message) => window.confirm(message),
}: {
  confirm?: (message: string) => boolean;
}) {
  const { apiBaseUrl } = useRuntimeConfig();
  const { remote, reload, update } = useRemote<UserSummary[]>("/api/users");
  const [notice, setNotice] = useState<string | null>(null);

  async function changeRole(user: UserSummary, role: string) {
    setNotice(null);
    const result = await apiRequest({ apiBaseUrl }, `/api/users/${user.id}`, {
      method: "PATCH",
      body: { role },
    });
    if (result.kind === "ok") {
      update((users) =>
        users.map((u) =>
          u.id === user.id ? { ...u, role: role as UserSummary["role"] } : u,
        ),
      );
      return;
    }
    setNotice(userActionMessage(result)); // the select stays at the stored role
    if (result.kind === "error" && result.status === 404) void reload();
  }

  async function remove(user: UserSummary) {
    if (!confirm(`Delete ${user.email}? Their sessions end immediately.`))
      return;
    setNotice(null);
    const result = await apiRequest({ apiBaseUrl }, `/api/users/${user.id}`, {
      method: "DELETE",
    });
    if (result.kind === "ok") {
      update((users) => users.filter((u) => u.id !== user.id));
      return;
    }
    setNotice(userActionMessage(result));
    if (result.kind === "error" && result.status === 404) void reload();
  }

  if (remote.status === "loading") return <p>Loading…</p>;
  if (remote.status === "error") return <p role="alert">{remote.message}</p>;

  return (
    <section>
      {notice ? <p role="alert">{notice}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Email</th>
            <th>Created</th>
            <th>Role</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {remote.data.map((user) => (
            <tr key={user.id}>
              <td>{user.email}</td>
              <td>{formatTime(user.created_at)}</td>
              <td>
                <select
                  aria-label={`Role of ${user.email}`}
                  value={user.role}
                  onChange={(e) => void changeRole(user, e.target.value)}
                >
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <button
                  type="button"
                  aria-label={`Delete ${user.email}`}
                  onClick={() => void remove(user)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
