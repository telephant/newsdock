"use client";
// Asks "are you sure?" before a destructive action (ADR-0022). `confirm(message,
// action)` returns a promise that resolves true only on the action button; Cancel,
// Escape and a click outside answer false. Pass `override` to answer without a dialog
// (tests and embedders). The message is a React text node, never HTML. No data
// fetching here.
import { useCallback, useState, type ReactNode } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export type ConfirmFn = (
  message: string,
  action?: string,
) => boolean | Promise<boolean>;

type Question = {
  message: string;
  action: string;
  resolve: (ok: boolean) => void;
  open: boolean;
};

export function useConfirm(override?: ConfirmFn): {
  confirm: (message: string, action?: string) => Promise<boolean>;
  dialog: ReactNode;
} {
  const [question, setQuestion] = useState<Question | null>(null);

  const confirm = useCallback(
    (message: string, action = "Confirm") => {
      if (override) return Promise.resolve(override(message, action));
      return new Promise<boolean>((resolve) =>
        setQuestion({ message, action, resolve, open: true }),
      );
    },
    [override],
  );

  function settle(ok: boolean) {
    // resolving twice is harmless; the text stays while the dialog fades out
    question?.resolve(ok);
    setQuestion((q) => (q ? { ...q, open: false } : q));
  }

  const dialog = (
    <AlertDialog
      open={question?.open ?? false}
      onOpenChange={(open) => {
        if (!open) settle(false);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Are you sure?</AlertDialogTitle>
          <AlertDialogDescription>{question?.message}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={() => settle(true)}>
            {question?.action}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return { confirm, dialog };
}
