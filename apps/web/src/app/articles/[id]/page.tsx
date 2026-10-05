import { Detail } from "@/features/article/Detail";

export default async function ArticlePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <main>
      <Detail articleId={id} />
    </main>
  );
}
