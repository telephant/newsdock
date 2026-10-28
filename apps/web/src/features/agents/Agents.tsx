"use client";
// Agents and API keys (AC-11): every signed-in user sees and manages their own agents
// (the owner role sees all, with the creator, ADR-0023). A key secret is shown exactly once,
// right after it is issued: it lives only in this component's state, never in the
// list (the API does not return it again), and is dropped on dismiss, on the next
// issued key and when the page unmounts. All text is escaped by React.
import { useId, useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { type ConfirmFn, useConfirm } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ListSkeleton } from "@/components/ListSkeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { agentActionMessage, formatTime } from "../admin/messages";
import { useRemote } from "../admin/useRemote";
import { useSession } from "../auth/SessionProvider";

type AgentSummary = components["schemas"]["AgentSummary"];
type IssuedAgent = components["schemas"]["IssuedAgent"];
type IssuedKey = components["schemas"]["IssuedKey"];

type Shown = { agent: string; key: string };

export function Agents({
  confirm: answer,
  copy = (text) => navigator.clipboard.writeText(text),
}: {
  confirm?: ConfirmFn;
  copy?: (text: string) => Promise<void>;
}) {
  const { apiBaseUrl } = useRuntimeConfig();
  const { confirm, dialog } = useConfirm(answer);
  const nameId = useId();
  const { remote, reload } = useRemote<AgentSummary[]>("/api/admin/agents");
  const session = useSession();
  // only the owner role receives other users' agents, so only it needs a creator
  const showCreator =
    session.status === "user" && session.user.role === "owner";
  const [name, setName] = useState("");
  const [shown, setShown] = useState<Shown | null>(null);
  const [copied, setCopied] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  function show(next: Shown | null) {
    setShown(next);
    setCopied(false);
  }

  async function run(path: string, init: { method: string; body?: unknown }) {
    setNotice(null);
    const result = await apiRequest({ apiBaseUrl }, path, init);
    if (result.kind !== "ok") {
      setNotice(agentActionMessage(result));
      if (result.kind === "error" && result.status === 404) void reload();
    }
    return result;
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await run("/api/admin/agents", {
      method: "POST",
      body: { name },
    });
    if (result.kind === "ok") {
      const issued = result.data as IssuedAgent;
      show({ agent: issued.name, key: issued.api_key });
      setName("");
      void reload();
    }
  }

  async function newKey(agent: AgentSummary) {
    const result = await run(`/api/admin/agents/${agent.agent_id}/keys`, {
      method: "POST",
    });
    if (result.kind === "ok") {
      show({ agent: agent.name, key: (result.data as IssuedKey).api_key });
      void reload();
    }
  }

  async function revoke(agent: AgentSummary, keyId: string, prefix: string) {
    if (
      !(await confirm(
        `Revoke key ${prefix} of ${agent.name}? It stops working at once.`,
        "Revoke",
      ))
    )
      return;
    const result = await run(
      `/api/admin/agents/${agent.agent_id}/keys/${keyId}`,
      { method: "DELETE" },
    );
    if (result.kind === "ok") void reload();
  }

  async function setEnabled(agent: AgentSummary, enable: boolean) {
    const verb = enable ? "enable" : "disable";
    const result = await run(`/api/admin/agents/${agent.agent_id}/${verb}`, {
      method: "POST",
    });
    if (result.kind === "ok") void reload();
  }

  async function copyKey(key: string) {
    await copy(key);
    setCopied(true);
  }

  if (remote.status === "loading") return <ListSkeleton rows={3} />;
  if (remote.status === "error") return <ErrorAlert message={remote.message} />;

  return (
    <section className="flex flex-col gap-6">
      <Card>
        <CardContent>
          <form
            onSubmit={create}
            aria-label="new agent"
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
          >
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor={nameId}>Agent name</Label>
              <Input
                id={nameId}
                name="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. demo-financial"
                required
              />
            </div>
            <Button type="submit">Create agent</Button>
          </form>
        </CardContent>
      </Card>

      {notice ? <ErrorAlert message={notice} /> : null}

      {shown ? (
        <Card
          role="status"
          aria-label="new key"
          className="ring-2 ring-primary"
        >
          <CardHeader>
            <CardTitle>New key for {shown.agent}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">
              Copy it now: it is shown only once and cannot be recovered. Only a
              hash is stored.
            </p>
            <code className="rounded-lg bg-muted p-3 font-mono text-sm break-all">
              {shown.key}
            </code>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" onClick={() => void copyKey(shown.key)}>
                Copy key
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => show(null)}
              >
                I have copied it
              </Button>
              {copied ? (
                <p className="text-sm text-primary-text">Copied.</p>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {remote.data.length === 0 ? (
        <EmptyState
          title="You have no agents yet."
          description="Create the first agent above to get an API key."
        />
      ) : (
        <ul className="flex flex-col gap-4">
          {remote.data.map((agent) => (
            <li key={agent.agent_id}>
              <Card>
                <CardHeader className="flex flex-wrap items-center gap-2">
                  <CardTitle className="break-all">{agent.name}</CardTitle>
                  {showCreator ? (
                    <p className="text-sm text-muted-foreground">
                      Created by{" "}
                      <span className="break-all">
                        {agent.owner_email ?? "no owner"}
                      </span>
                    </p>
                  ) : null}
                  <Badge
                    variant={
                      agent.status === "active" ? "default" : "secondary"
                    }
                  >
                    {agent.status}
                  </Badge>
                  <div className="ml-auto flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      aria-label={`New key for ${agent.name}`}
                      onClick={() => void newKey(agent)}
                    >
                      New key
                    </Button>
                    {agent.status === "active" ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-label={`Disable ${agent.name}`}
                        onClick={() => void setEnabled(agent, false)}
                      >
                        Disable
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-label={`Enable ${agent.name}`}
                        onClick={() => void setEnabled(agent, true)}
                      >
                        Enable
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <Table className="sm:min-w-[32rem]">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Key</TableHead>
                        <TableHead className="max-sm:hidden">Created</TableHead>
                        <TableHead className="max-sm:hidden">
                          Last used
                        </TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {agent.keys.map((key) => (
                        <TableRow key={key.key_id}>
                          <TableCell>
                            <code className="font-mono text-sm">
                              {key.prefix}
                            </code>
                          </TableCell>
                          <TableCell className="text-muted-foreground max-sm:hidden">
                            {formatTime(key.created_at)}
                          </TableCell>
                          <TableCell className="text-muted-foreground max-sm:hidden">
                            {key.last_used_at
                              ? formatTime(key.last_used_at)
                              : "never used"}
                          </TableCell>
                          <TableCell>
                            {key.revoked_at ? (
                              <Badge
                                variant="destructive"
                                title={`revoked ${formatTime(key.revoked_at)}`}
                              >
                                revoked
                              </Badge>
                            ) : (
                              <Badge variant="outline">valid</Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            {key.revoked_at ? null : (
                              <Button
                                type="button"
                                variant="destructive"
                                size="sm"
                                aria-label={`Revoke key ${key.prefix}`}
                                onClick={() =>
                                  void revoke(agent, key.key_id, key.prefix)
                                }
                              >
                                Revoke
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
      {dialog}
    </section>
  );
}
