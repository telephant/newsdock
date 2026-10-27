"use client";
// Login (AC-8). The cookie is set by the API; success is a full page navigation so
// the session state and the gate start fresh. Errors are shown as text, one generic
// message for wrong credentials (the API gives the same answer for unknown emails).
import Link from "next/link";
import { useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { apiRequest } from "@/lib/client/api";
import { loginMessage } from "./messages";

export function LoginForm({
  next,
  navigate = (url) => window.location.assign(url),
}: {
  next: string; // already checked with safeNext by the page
  navigate?: (url: string) => void;
}) {
  const { apiBaseUrl } = useRuntimeConfig();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    const result = await apiRequest({ apiBaseUrl }, "/api/auth/login", {
      method: "POST",
      body: { email, password },
    });
    if (result.kind === "ok") {
      navigate(next);
      return; // stay disabled: the page is about to be replaced
    }
    setError(loginMessage(result));
    setPassword("");
    setPending(false);
  }

  return (
    <form onSubmit={onSubmit} aria-label="log in">
      <label>
        Email
        <input
          name="email"
          type="text"
          inputMode="email"
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </label>
      <label>
        Password
        <input
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </label>
      {error ? <p role="alert">{error}</p> : null}
      <button type="submit" disabled={pending}>
        {pending ? "Logging in…" : "Log in"}
      </button>
      <p>
        No account yet? <Link href="/signup">Sign up</Link>
      </p>
    </form>
  );
}
