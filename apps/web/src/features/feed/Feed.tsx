"use client";
// Feed (AC-12): newest first, filters, agent score badge, keyset "load more",
// 60 s polling refresh. All text rendered via React (escaped, never HTML).
import { useCallback, useEffect, useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { fetchFeed, type ArticleSummary, type FeedFilters } from "./api";
import { ArticleItem } from "./ArticleItem";

export function Feed() {
  const { apiBaseUrl, pollMs, pageSize } = useRuntimeConfig();
  const [filters, setFilters] = useState<FeedFilters>({});
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const page = await fetchFeed({ apiBaseUrl, pageSize }, filters);
      setArticles(page.articles);
      setNextBefore(page.next_before);
      setError(null);
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
    <section>
      <form onSubmit={onFilter} aria-label="filters">
        <input name="theme" placeholder="theme (e.g. ECON_INFLATION)" />
        <input name="domain" placeholder="domain" />
        <input name="text" placeholder="title contains…" />
        <button type="submit">Filter</button>
      </form>
      {error ? <p role="alert">{error}</p> : null}
      <ol>
        {articles.map((article) => (
          <ArticleItem key={article.article_id} article={article} />
        ))}
      </ol>
      {nextBefore ? (
        <button onClick={() => void loadMore()}>Load more</button>
      ) : null}
    </section>
  );
}
