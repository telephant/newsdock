import { PageHeader } from "@/components/PageHeader";
import { Live } from "@/features/live/Live";

export default function LivePage() {
  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader
        title="Live"
        description="New articles appear here as they arrive."
      />
      <Live />
    </div>
  );
}
