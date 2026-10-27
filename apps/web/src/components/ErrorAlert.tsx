// Error message block (role="alert"). The message is rendered as text, never HTML.
import { CircleAlert } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

export function ErrorAlert({ message }: { message: string }) {
  return (
    <Alert variant="destructive" className="mb-4">
      <CircleAlert aria-hidden />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}
