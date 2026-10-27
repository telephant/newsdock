import { PageHeader } from "@/components/PageHeader";
import { Subscriptions } from "@/features/subscriptions/Subscriptions";

export default function SubscriptionsPage() {
  return (
    <>
      <PageHeader
        title="Subscriptions"
        description="Saved filters owned by agents. You can remove them here."
      />
      <Subscriptions />
    </>
  );
}
