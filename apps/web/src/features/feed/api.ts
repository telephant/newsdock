// Typed fetchers over the generated OpenAPI types (lib/api is generated only).
import type { components } from "@/lib/api/types";

export type ArticleSummary = components["schemas"]["ArticleSummary"];
export type ArticleDetail = components["schemas"]["ArticleDetail"];
export type FeedPage = components["schemas"]["FeedPage"];

// Where and how much to fetch comes from the runtime config (ADR-0014).
export type ApiConfig = { apiBaseUrl: string; pageSize?: number };

export type FeedFilters = {
  theme?: string;
  domain?: string;
  text?: string;
  before?: string;
};

export async function fetchFeed(
  config: ApiConfig,
  filters: FeedFilters,
): Promise<FeedPage> {
  const params = new URLSearchParams();
  if (config.pageSize) params.set("limit", String(config.pageSize));
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  const response = await fetch(`${config.apiBaseUrl}/api/articles?${params}`);
  if (!response.ok) throw new Error(`feed failed: ${response.status}`);
  return (await response.json()) as FeedPage;
}

export async function fetchArticle(
  config: ApiConfig,
  articleId: string,
): Promise<ArticleDetail> {
  const response = await fetch(
    `${config.apiBaseUrl}/api/articles/${encodeURIComponent(articleId)}`,
  );
  if (!response.ok) throw new Error(`article failed: ${response.status}`);
  return (await response.json()) as ArticleDetail;
}
