"use client";
// Agents and API keys (AC-11, admin and owner). A key secret is shown exactly once,
// right after it is issued: it lives only in this component's state, never in the
// list (the API does not return it again), and is dropped on dismiss, on the next
// issued key and when the page unmounts. All text is escaped by React.
import { useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import type { components } from "@/lib/api/types";
import { apiRequest } from "@/lib/client/api";
import { agentActionMessage, formatTime } from "../admin/messages";
import { useRemote } from "../admin/useRemote";

type AgentSummary = components["schemas"]["AgentSummary"];
type IssuedAgent = components["schemas"]["IssuedAgent"];
type IssuedKey = components["schemas"]["IssuedKey"];

type Shown = { agent: string; key: string };

export function Agents({
  confirm = (message) => window.confirm(message),
  copy = (text) => navigator.clipboard.writeText(text),
}: {
  confirm?: (message: string) => boolean;
  copy?: (text: string) => Promise<void>;
}) {
  const { apiBaseUrl } = useRuntimeConfig();
  const { remote, reload } = useRemote<AgentSummary[]>("/api/admin/agents");
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
      !confirm(
        `Revoke key ${prefix} of ${agent.name}? It stops working at once.`,
      )
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

  if (remote.status === "loading") return <p>Loading…</p>;
  if (remote.status === "error") return <p role="alert">{remote.message}</p>;

  return (
    <section>
      <form onSubmit={create} aria-label="new agent">
        <label>
          Agent name
          <input
            name="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. demo-financial"
            required
          />
        </label>
        <button type="submit">Create agent</button>
      </form>

      {notice ? <p role="alert">{notice}</p> : null}

      {shown ? (
        <section role="status" aria-label="new key">
          <h2>New key for {shown.agent}</h2>
          <p>
            Copy it now: it is shown only once and cannot be recovered. Only a
            hash is stored.
          </p>
          <code>{shown.key}</code>{" "}
          <button type="button" onClick={() => void copyKey(shown.key)}>
            Copy key
          </button>{" "}
          <button type="button" onClick={() => show(null)}>
            I have copied it
          </button>
          {copied ? <p>Copied.</p> : null}
        </section>
      ) : null}

      <ul>
        {remote.data.map((agent) => (
          <li key={agent.agent_id}>
            <strong>{agent.name}</strong> <em>{agent.status}</em>{" "}
            <button
              type="button"
              aria-label={`New key for ${agent.name}`}
              onClick={() => void newKey(agent)}
            >
              New key
            </button>{" "}
            {agent.status === "active" ? (
              <button
                type="button"
                aria-label={`Disable ${agent.name}`}
                onClick={() => void setEnabled(agent, false)}
              >
                Disable
              </button>
            ) : (
              <button
                type="button"
                aria-label={`Enable ${agent.name}`}
                onClick={() => void setEnabled(agent, true)}
              >
                Enable
              </button>
            )}
            <ul>
              {agent.keys.map((key) => (
                <li key={key.key_id}>
                  <code>{key.prefix}</code> created {formatTime(key.created_at)}
                  ,{" "}
                  {key.last_used_at
                    ? `last used ${formatTime(key.last_used_at)}`
                    : "never used"}
                  {key.revoked_at ? (
                    <span> (revoked {formatTime(key.revoked_at)})</span>
                  ) : (
                    <>
                      {" "}
                      <button
                        type="button"
                        aria-label={`Revoke key ${key.prefix}`}
                        onClick={() =>
                          void revoke(agent, key.key_id, key.prefix)
                        }
                      >
                        Revoke
                      </button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  );
}
