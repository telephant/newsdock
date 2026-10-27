"use client";
// Subscriptions (AC-12, admin and owner): every agent's saved filters, with delete.
// Agents own and create their subscriptions; this screen only shows and removes them.
// All text is escaped by React.
import { useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { type ConfirmFn, useConfirm } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ListSkeleton } from "@/components/ListSkeleton";
import { Badge } from "@/components/ui/badge";
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
import { adminMessage, formatTime } from "../admin/messages";
import { useRemote } from "../admin/useRemote";

type AdminSubscription = components["schemas"]["AdminSubscription"];

export function Subscriptions({ confirm: answer }: { confirm?: ConfirmFn }) {
  const { apiBaseUrl } = useRuntimeConfig();
  const { confirm, dialog } = useConfirm(answer);
  const { remote, update } = useRemote<AdminSubscription[]>(
    "/api/admin/subscriptions",
  );
  const [notice, setNotice] = useState<string | null>(null);

  async function remove(sub: AdminSubscription) {
    if (
      !(await confirm(
        `Delete the subscription of ${sub.agent_name}? Its open stream ends shortly.`,
        "Delete",
      ))
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

  if (remote.status === "loading") return <ListSkeleton rows={3} />;
  if (remote.status === "error") return <ErrorAlert message={remote.message} />;
  if (remote.data.length === 0 && !notice) {
    return (
      <EmptyState
        title="No subscriptions yet."
        description="Agents create their own saved filters; they show up here."
      />
    );
  }

  return (
    <section className="flex flex-col gap-4">
      {notice ? <ErrorAlert message={notice} /> : null}
      <div className="rounded-xl border border-border bg-card">
        <Table className="sm:min-w-[34rem]">
          <TableHeader>
            <TableRow>
              <TableHead>Agent</TableHead>
              <TableHead>Filter</TableHead>
              <TableHead className="max-sm:hidden">Created</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {remote.data.map((sub) => {
              const fields = Object.entries(sub.filter);
              return (
                <TableRow key={sub.id}>
                  <TableCell className="font-medium">
                    {sub.agent_name}
                  </TableCell>
                  <TableCell className="whitespace-normal">
                    {fields.length === 0 ? (
                      <span className="text-muted-foreground">
                        any article (no filter)
                      </span>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {fields.map(([key, value]) => (
                          <Badge
                            key={key}
                            variant="secondary"
                            className="h-auto max-w-full break-all whitespace-normal"
                          >{`${key}: ${String(value)}`}</Badge>
                        ))}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground max-sm:hidden">
                    {formatTime(sub.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      aria-label={`Delete subscription of ${sub.agent_name}`}
                      onClick={() => void remove(sub)}
                    >
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      {dialog}
    </section>
  );
}
