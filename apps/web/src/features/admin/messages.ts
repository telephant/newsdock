// Messages for the management screens. Plain strings, rendered as React text nodes,
// so even an unexpected server code stays inert (NFR-4).
import type { ApiResult } from "@/lib/client/api";

type Failure = Exclude<ApiResult<unknown>, { kind: "ok" }>;

export function adminMessage(failure: Failure): string {
  if (failure.kind === "unreachable") {
    return "Cannot reach the server. Reload to try again.";
  }
  if (failure.status === 403) {
    return "You do not have permission to use this screen.";
  }
  if (failure.status === 401) return "Your session has ended. Log in again.";
  return `Something went wrong (${failure.detail}).`;
}

export function userActionMessage(failure: Failure): string {
  if (failure.kind === "error" && failure.detail === "last_owner") {
    return "That would leave no owner. Make another user an owner first (the last owner cannot be demoted or deleted).";
  }
  if (failure.kind === "error" && failure.status === 404) {
    return "That user no longer exists. The list was refreshed.";
  }
  return adminMessage(failure);
}

export function agentActionMessage(failure: Failure): string {
  if (failure.kind === "error" && failure.detail === "name_taken") {
    return "An agent with that name already exists.";
  }
  if (failure.kind === "error" && failure.status === 422) {
    return "Use 1 to 40 lowercase letters, digits, _ or - for the agent name.";
  }
  if (failure.kind === "error" && failure.status === 404) {
    return "That agent or key no longer exists. The list was refreshed.";
  }
  return adminMessage(failure);
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}
