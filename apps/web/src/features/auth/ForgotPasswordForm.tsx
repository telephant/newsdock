"use client";
// Forgot password, step 1 (AC-16): ask for a code. The answer is the same for every
// address, so the confirmation never says whether an account exists.
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
import { forgotMessage } from "./messages";

export function ForgotPasswordForm() {
  const { apiBaseUrl } = useRuntimeConfig();
  const id = useId();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    const result = await apiRequest(
      { apiBaseUrl },
      "/api/auth/forgot-password",
      {
        method: "POST",
        body: { email },
      },
    );
    setPending(false);
    if (result.kind === "ok") {
      setSent(true);
      return;
    }
    setError(forgotMessage(result));
  }

  return (
    <Card>
      <CardContent>
        <form
          onSubmit={onSubmit}
          aria-label="request a reset code"
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
              aria-invalid={error ? true : undefined}
              required
            />
          </div>
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          {sent ? (
            <div role="status" className="text-sm">
              <p>
                If that email has an account, a code is on its way. It works for
                a few minutes.
              </p>
              <p className="mt-2">
                <Link
                  href={`/reset-password?email=${encodeURIComponent(email)}`}
                  className={footerLink}
                >
                  Enter the code
                </Link>
              </p>
            </div>
          ) : null}
          <Button type="submit" size="lg" disabled={pending} className="w-full">
            {pending ? "Sending…" : "Send code"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            <Link href="/login" className={footerLink}>
              Back to log in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
