"use client";
// Sign-up (AC-8, spec D-3: open self-sign-up). A new account is a viewer, except the
// very first one, which becomes the owner; the server decides. Success goes to /login.
import Link from "next/link";
import { useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { apiRequest } from "@/lib/client/api";
import { signupMessage } from "./messages";

export function SignupForm({
  navigate = (url) => window.location.assign(url),
}: {
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
    const result = await apiRequest({ apiBaseUrl }, "/api/auth/signup", {
      method: "POST",
      body: { email, password },
    });
    if (result.kind === "ok") {
      navigate("/login");
      return;
    }
    setError(signupMessage(result));
    setPending(false);
  }

  return (
    <form onSubmit={onSubmit} aria-label="sign up">
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
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </label>
      {error ? <p role="alert">{error}</p> : null}
      <button type="submit" disabled={pending}>
        {pending ? "Signing up…" : "Sign up"}
      </button>
      <p>
        Already have an account? <Link href="/login">Log in</Link>
      </p>
    </form>
  );
}
