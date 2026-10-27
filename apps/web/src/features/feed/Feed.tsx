"use client";
// Feed (AC-12): newest first, filters, agent score badge, keyset "load more",
// 60 s polling refresh. All text rendered via React (escaped, never HTML).
import { useCallback, useEffect, useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { EmptyState } from "@/components/EmptyState";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ListSkeleton } from "@/components/ListSkeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchFeed, type ArticleSummary, type FeedFilters } from "./api";
import { ArticleItem } from "./ArticleItem";

export function Feed() {
  const { apiBaseUrl, pollMs, pageSize } = useRuntimeConfig();
  const [filters, setFilters] = useState<FeedFilters>({});
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const page = await fetchFeed({ apiBaseUrl, pageSize }, filters);
      setArticles(page.articles);
      setNextBefore(page.next_before);
      setError(null);
      setLoaded(true);
    } catch (e) {
      setError(String(e));
    }
  }, [filters, apiBaseUrl, pageSize]);

  useEffect(() => {
    // initial fetch + 60 s polling; load() is async, so setState happens in
    // the promise callback, not synchronously inside the effect body
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const timer = setInterval(() => void load(), pollMs);
    return () => clearInterval(timer);
  }, [load, pollMs]);

  async function loadMore() {
    if (!nextBefore) return;
    const page = await fetchFeed(
      { apiBaseUrl, pageSize },
      { ...filters, before: nextBefore },
    );
    setArticles((current) => [...current, ...page.articles]);
    setNextBefore(page.next_before);
  }

  function onFilter(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setFilters({
      theme: String(data.get("theme") ?? "") || undefined,
      domain: String(data.get("domain") ?? "") || undefined,
      text: String(data.get("text") ?? "") || undefined,
    });
  }

  return (
    <section className="flex flex-col gap-4">
      <Card className="py-3">
        <CardContent className="px-4">
          <form
            onSubmit={onFilter}
            aria-label="filters"
            className="flex flex-col gap-2 sm:flex-row"
          >
            <Input
              name="theme"
              aria-label="Theme"
              placeholder="theme (e.g. ECON_INFLATION)"
            />
            <Input name="domain" aria-label="Domain" placeholder="domain" />
            <Input
              name="text"
              aria-label="Title contains"
              placeholder="title contains…"
            />
            <Button type="submit">Filter</Button>
          </form>
        </CardContent>
      </Card>
      {error ? <ErrorAlert message={error} /> : null}
      {!loaded && !error ? <ListSkeleton /> : null}
      {loaded && articles.length === 0 ? (
        <EmptyState
          title="No articles found"
          description="Try different filters, or check back in a few minutes."
        />
      ) : null}
      <ol className="flex flex-col gap-3">
        {articles.map((article) => (
          <ArticleItem key={article.article_id} article={article} />
        ))}
      </ol>
      {nextBefore ? (
        <Button
          variant="outline"
          className="self-center"
          onClick={() => void loadMore()}
        >
          Load more
        </Button>
      ) : null}
    </section>
  );
}
