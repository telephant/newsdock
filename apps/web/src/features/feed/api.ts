// Typed fetchers over the generated OpenAPI types (lib/api is generated only).
// They go through the credentialed client, so the session cookie is sent and a 401
// sends the user to /login.
import type { components } from "@/lib/api/types";
import { apiFetch } from "@/lib/client/api";

// The feed is documented as ArticleSummaryTone / FeedPageTone: the same article with
// the four tone numbers as optional keys (ADR-0030). The names here stay as they were.
export type ArticleSummary = components["schemas"]["ArticleSummaryTone"];
export type ArticleDetail = components["schemas"]["ArticleDetail"];
export type FeedPage = components["schemas"]["FeedPageTone"];

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
  const response = await apiFetch(config, `/api/articles?${params}`);
  if (!response.ok) throw new Error(`feed failed: ${response.status}`);
  return (await response.json()) as FeedPage;
}

export async function fetchArticle(
  config: ApiConfig,
  articleId: string,
): Promise<ArticleDetail> {
  const response = await apiFetch(
    config,
    `/api/articles/${encodeURIComponent(articleId)}`,
  );
  if (!response.ok) throw new Error(`article failed: ${response.status}`);
  return (await response.json()) as ArticleDetail;
}
