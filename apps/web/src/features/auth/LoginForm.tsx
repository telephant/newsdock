"use client";
// Login (AC-8). The cookie is set by the API; success is a full page navigation so
// the session state and the gate start fresh. Errors are shown as text, one generic
// message for wrong credentials (the API gives the same answer for unknown emails).
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { apiRequest } from "@/lib/client/api";
import { CredentialForm, footerLink } from "./CredentialForm";
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
  const [resetOffered, setResetOffered] = useState(false);

  // The link shows only when the server has the feature on; any failure means no link.
  useEffect(() => {
    let live = true;
    apiRequest<{ password_reset_enabled: boolean }>(
      { apiBaseUrl },
      "/api/auth/options",
    ).then((result) => {
      if (live && result.kind === "ok") {
        setResetOffered(result.data.password_reset_enabled === true);
      }
    });
    return () => {
      live = false;
    };
  }, [apiBaseUrl]);

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
    <CredentialForm
      label="log in"
      email={email}
      onEmail={setEmail}
      password={password}
      onPassword={setPassword}
      passwordAutoComplete="current-password"
      error={error}
      pending={pending}
      submitLabel="Log in"
      pendingLabel="Logging in…"
      onSubmit={onSubmit}
      footer={
        <>
          No account yet?{" "}
          <Link href="/signup" className={footerLink}>
            Sign up
          </Link>
          {resetOffered ? (
            <>
              {" · "}
              <Link href="/forgot-password" className={footerLink}>
                Forgot password?
              </Link>
            </>
          ) : null}
        </>
      }
    />
  );
}
