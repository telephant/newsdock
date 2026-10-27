import { PageHeader } from "@/components/PageHeader";
import { Feed } from "@/features/feed/Feed";

export default function Home() {
  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader
        title="Latest news"
        description="Cleaned GDELT articles, newest first."
      />
      <Feed />
    </div>
  );
}
