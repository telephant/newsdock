import { PageHeader } from "@/components/PageHeader";
import { Agents } from "@/features/agents/Agents";

export default function AgentsPage() {
  return (
    <>
      <PageHeader
        title="Agents and keys"
        description="Register agents and issue API keys. A key is shown once."
      />
      <Agents />
    </>
  );
}
