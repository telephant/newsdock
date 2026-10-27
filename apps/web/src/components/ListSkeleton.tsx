// Placeholder rows while a list loads: three lines per row, announced as loading.
import { Skeleton } from "@/components/ui/skeleton";

export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-busy="true" className="flex flex-col gap-3">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }, (_, row) => (
        <div
          key={row}
          className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4"
        >
          <Skeleton className="h-5 w-4/5" />
          <Skeleton className="h-5 w-3/5" />
          <Skeleton className="h-4 w-2/5" />
        </div>
      ))}
    </div>
  );
}
