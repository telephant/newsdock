// Human messages for the API's stable error codes. Plain strings only: they are
// rendered as React text nodes, so even an unexpected server code stays inert (NFR-4).
import type { ApiResult } from "@/lib/client/api";

export function formatWait(seconds: number): string {
  if (seconds <= 90) return `${seconds} seconds`;
  return `about ${Math.ceil(seconds / 60)} minutes`;
}

type Failure = Exclude<ApiResult<unknown>, { kind: "ok" }>;

const UNREACHABLE =
  "Cannot reach the server. Check your connection and try again.";

export function loginMessage(failure: Failure): string {
  if (failure.kind === "unreachable") return UNREACHABLE;
  if (failure.status === 401) return "Wrong email or password.";
  if (failure.status === 429) {
    const wait = failure.retryAfter
      ? ` in ${formatWait(failure.retryAfter)}`
      : " later";
    return `Too many attempts. Try again${wait}.`;
  }
  if (failure.status === 422) return "Enter a valid email and password.";
  return `Something went wrong (${failure.detail}).`;
}

function waitText(failure: { retryAfter?: number }): string {
  return failure.retryAfter
    ? ` in ${formatWait(failure.retryAfter)}`
    : " later";
}

export function forgotMessage(failure: Failure): string {
  if (failure.kind === "unreachable") return UNREACHABLE;
  if (failure.status === 429)
    return `Too many requests. Try again${waitText(failure)}.`;
  if (failure.status === 422) return "Enter a valid email address.";
  if (failure.status === 503) {
    return "Password reset is not available on this server. Ask an owner to reset it.";
  }
  return `Something went wrong (${failure.detail}).`;
}

export function resetMessage(failure: Failure): string {
  if (failure.kind === "unreachable") return UNREACHABLE;
  if (failure.status === 400) {
    return "The code is wrong or has expired.";
  }
  if (failure.status === 429)
    return `Too many attempts. Try again${waitText(failure)}.`;
  if (failure.status === 422) {
    return failure.detail === "invalid_email"
      ? "Enter a valid email address."
      : "The password length is not accepted: use 10 to 128 characters (the minimum is set by the server).";
  }
  if (failure.status === 503) {
    return "Password reset is not available on this server. Ask an owner to reset it.";
  }
  return `Something went wrong (${failure.detail}).`;
}

export function signupMessage(failure: Failure): string {
  if (failure.kind === "unreachable") return UNREACHABLE;
  if (failure.status === 429) {
    const wait = failure.retryAfter
      ? ` in ${formatWait(failure.retryAfter)}`
      : " later";
    return `Too many sign-ups from here. Try again${wait}.`;
  }
  switch (failure.detail) {
    case "email_taken":
      return "That email is already registered. Try logging in instead.";
    case "invalid_email":
      return "Enter a valid email address.";
    case "invalid_password":
      return "The password length is not accepted: use 10 to 128 characters (the minimum is set by the server).";
    case "signup_closed":
      return "Sign-up is closed. Ask an owner for an account.";
    default:
      return `Something went wrong (${failure.detail}).`;
  }
}
