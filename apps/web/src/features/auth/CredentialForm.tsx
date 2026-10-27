"use client";
// Markup shared by the login and sign-up forms (ADR-0022): a card with labelled
// fields, an inline error tied to both fields, and a pending button. No logic here;
// the callers own state and submission. Everything shown is a React text node.
import { useId, type FormEvent, type ReactNode } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// Link style for the footer line ("No account yet? Sign up").
export const footerLink =
  "font-medium text-primary-text underline underline-offset-4 hover:no-underline focus-visible:rounded-sm focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none";

export function CredentialForm({
  label,
  email,
  onEmail,
  password,
  onPassword,
  passwordAutoComplete,
  error,
  pending,
  submitLabel,
  pendingLabel,
  onSubmit,
  footer,
}: {
  label: string; // accessible name of the form
  email: string;
  onEmail: (value: string) => void;
  password: string;
  onPassword: (value: string) => void;
  passwordAutoComplete: "current-password" | "new-password";
  error: string | null;
  pending: boolean;
  submitLabel: string;
  pendingLabel: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  footer: ReactNode;
}) {
  const id = useId();
  const errorId = `${id}-error`;
  const invalid = error ? true : undefined;
  const describedBy = error ? errorId : undefined;
  return (
    <Card>
      <CardContent>
        <form
          onSubmit={onSubmit}
          aria-label={label}
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
              onChange={(e) => onEmail(e.target.value)}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${id}-password`}>Password</Label>
            <Input
              id={`${id}-password`}
              name="password"
              type="password"
              autoComplete={passwordAutoComplete}
              value={password}
              onChange={(e) => onPassword(e.target.value)}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              required
            />
          </div>
          {error ? (
            <Alert variant="destructive" id={errorId}>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <Button type="submit" size="lg" disabled={pending} className="w-full">
            {pending ? pendingLabel : submitLabel}
          </Button>
          <p className="text-center text-sm text-muted-foreground">{footer}</p>
        </form>
      </CardContent>
    </Card>
  );
}
