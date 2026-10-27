// Friendly "nothing here" block. Text only; no data fetching.
import { Inbox } from "lucide-react";

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div
      data-slot="empty-state"
      className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border px-6 py-12 text-center"
    >
      <Inbox aria-hidden className="size-8 text-muted-foreground" />
      <p className="font-medium">{title}</p>
      {description ? (
        <p className="text-sm text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}
