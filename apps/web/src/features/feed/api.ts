// Typed fetchers over the generated OpenAPI types (lib/api is generated only).
import type { components } from "@/lib/api/types";

export type ArticleSummary = components["schemas"]["ArticleSummary"];
export type ArticleDetail = components["schemas"]["ArticleDetail"];
export type FeedPage = components["schemas"]["FeedPage"];

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export type FeedFilters = {
  theme?: string;
  domain?: string;
  text?: string;
  before?: string;
};

export async function fetchFeed(filters: FeedFilters): Promise<FeedPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  const response = await fetch(`${API_BASE}/api/articles?${params}`);
  if (!response.ok) throw new Error(`feed failed: ${response.status}`);
  return (await response.json()) as FeedPage;
}

export async function fetchArticle(articleId: string): Promise<ArticleDetail> {
  const response = await fetch(
    `${API_BASE}/api/articles/${encodeURIComponent(articleId)}`,
  );
  if (!response.ok) throw new Error(`article failed: ${response.status}`);
  return (await response.json()) as ArticleDetail;
}
