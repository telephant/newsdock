"use client";
// Forgot password, step 2 (AC-16): the emailed code and a new password. A wrong and an
// expired code get the same text (the API answers both with one 400).
import Link from "next/link";
import { useId, useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiRequest } from "@/lib/client/api";
import { footerLink } from "./CredentialForm";
import { resetMessage } from "./messages";

export function ResetPasswordForm({ initialEmail }: { initialEmail: string }) {
  const { apiBaseUrl } = useRuntimeConfig();
  const id = useId();
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [retryable, setRetryable] = useState(false);
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    const result = await apiRequest(
      { apiBaseUrl },
      "/api/auth/reset-password",
      {
        method: "POST",
        body: { email, code, password },
      },
    );
    setPending(false);
    if (result.kind === "ok") {
      setDone(true);
      return;
    }
    setError(resetMessage(result));
    setRetryable(result.kind === "error" && result.status === 400);
    setPassword("");
  }

  if (done) {
    return (
      <Card>
        <CardContent>
          <div role="status" className="flex flex-col gap-3 text-sm">
            <p>Password changed. You can log in with the new password now.</p>
            <Link href="/login" className={footerLink}>
              Log in
            </Link>
          </div>
        </CardContent>
      </Card>
    );
  }

  const invalid = error ? true : undefined;
  return (
    <Card>
      <CardContent>
        <form
          onSubmit={onSubmit}
          aria-label="set a new password"
          aria-busy={pending}
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${id}-email`}>Email</Label>
            <Input
              id={`${id}-email`}
              name="email"
              type="text"
              inputMode="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={invalid}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${id}-code`}>Code</Label>
            <Input
              id={`${id}-code`}
              name="code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              aria-invalid={invalid}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${id}-password`}>New password</Label>
            <Input
              id={`${id}-password`}
              name="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={invalid}
              required
            />
          </div>
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <Button type="submit" size="lg" disabled={pending} className="w-full">
            {pending ? "Changing…" : "Change password"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            {retryable ? (
              <>
                <Link href="/forgot-password" className={footerLink}>
                  Request a new code
                </Link>
                {" · "}
              </>
            ) : null}
            <Link href="/login" className={footerLink}>
              Back to log in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
