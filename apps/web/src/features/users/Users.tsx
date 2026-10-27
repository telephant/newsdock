"use client";
// Users (AC-10, owner only): change roles and delete accounts. The API enforces the
// permission and the "last owner stays" rule; this screen shows its answers and keeps
// the select in line with what the server accepted. All text is escaped by React.
import { useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { type ConfirmFn, useConfirm } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ListSkeleton } from "@/components/ListSkeleton";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { components } from "@/lib/api/types";
import { apiRequest } from "@/lib/client/api";
import { formatTime, userActionMessage } from "../admin/messages";
import { useRemote } from "../admin/useRemote";

type UserSummary = components["schemas"]["UserSummary"];
const ROLES = ["owner", "admin", "viewer"] as const;

export function Users({ confirm: answer }: { confirm?: ConfirmFn }) {
  const { apiBaseUrl } = useRuntimeConfig();
  const { confirm, dialog } = useConfirm(answer);
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
    if (
      !(await confirm(
        `Delete ${user.email}? Their sessions end immediately.`,
        "Delete",
      ))
    )
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

  if (remote.status === "loading") return <ListSkeleton rows={4} />;
  if (remote.status === "error") return <ErrorAlert message={remote.message} />;

  return (
    <section className="flex flex-col gap-4">
      {notice ? <ErrorAlert message={notice} /> : null}
      {remote.data.length === 0 ? (
        <EmptyState title="No users yet" />
      ) : (
        <div className="rounded-xl border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Role</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {remote.data.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium break-all whitespace-normal">
                    {user.email}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatTime(user.created_at)}
                  </TableCell>
                  <TableCell>
                    <select
                      aria-label={`Role of ${user.email}`}
                      value={user.role}
                      onChange={(e) => void changeRole(user, e.target.value)}
                      className="h-8 rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      {ROLES.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      aria-label={`Delete ${user.email}`}
                      onClick={() => void remove(user)}
                    >
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {dialog}
    </section>
  );
}
