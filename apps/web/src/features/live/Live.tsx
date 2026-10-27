"use client";
// Live feed (AC-15): new articles appear without a reload. One EventSource to
// /api/live with the session cookie (ADR-0021). The browser reconnects on its own and
// resends Last-Event-ID, so a short drop loses nothing. When the stream is closed for
// good the page cannot tell why (EventSource hides the status), so it checks the
// session: a lost one goes to /login, otherwise a Reconnect button is offered.
// All text is rendered by React (escaped, never HTML).
import { useEffect, useState } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { apiRequest, type ClientDeps } from "@/lib/client/api";
import type { ArticleSummary } from "@/features/feed/api";
import { ArticleItem } from "@/features/feed/ArticleItem";

// The part of EventSource the page uses, so tests can drive it (jsdom has none).
export type EventSourceLike = {
  addEventListener(
    type: string,
    listener: (event: { data: string }) => void,
  ): void;
  close(): void;
  onopen: (() => void) | null;
  onerror: (() => void) | null;
  readyState: number;
};
export type CreateSource = (
  url: string,
  init?: { withCredentials?: boolean },
) => EventSourceLike;

const defaultCreate: CreateSource = (url, init) =>
  new EventSource(url, init) as unknown as EventSourceLike;

const CLOSED = 2; // EventSource.CLOSED
const MAX_ITEMS = 200; // a tab left open for days must not grow without bound

type Status = "connecting" | "live" | "reconnecting" | "closed";

const STATUS_TEXT: Record<Status, string> = {
  connecting: "Connecting…",
  live: "Live: new articles appear here as they arrive.",
  reconnecting: "Connection lost, reconnecting…",
  closed: "Disconnected.",
};

// Dot colours come from tokens only; reconnecting pulses unless motion is reduced.
const DOT_CLASS: Record<Status, string> = {
  connecting: "bg-muted-foreground",
  live: "bg-primary",
  reconnecting: "bg-muted-foreground motion-safe:animate-pulse",
  closed: "bg-destructive",
};

function parseArticle(data: string): ArticleSummary | null {
  try {
    const value: unknown = JSON.parse(data);
    if (
      value &&
      typeof value === "object" &&
      typeof (value as ArticleSummary).article_id === "string" &&
      typeof (value as ArticleSummary).title === "string"
    ) {
      return value as ArticleSummary;
    }
  } catch {
    // a malformed event is skipped; the stream goes on
  }
  return null;
}

export function Live({
  createSource = defaultCreate,
  deps,
}: {
  createSource?: CreateSource;
  deps?: ClientDeps; // test seam: fetch, navigate, location
}) {
  const { apiBaseUrl } = useRuntimeConfig();
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [status, setStatus] = useState<Status>("connecting");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const source = createSource(`${apiBaseUrl}/api/live`, {
      withCredentials: true,
    });
    source.onopen = () => setStatus("live");
    source.onerror = () => {
      if (source.readyState !== CLOSED) {
        setStatus("reconnecting"); // the browser is retrying by itself
        return;
      }
      setStatus("closed");
      // a 401 here sends the visitor to /login (client); otherwise stay and offer a retry
      void apiRequest({ apiBaseUrl }, "/api/auth/me", undefined, deps);
    };
    source.addEventListener("article", (event) => {
      const article = parseArticle(event.data);
      if (!article) return;
      setArticles((current) =>
        [
          article,
          ...current.filter((a) => a.article_id !== article.article_id),
        ].slice(0, MAX_ITEMS),
      );
    });
    return () => source.close();
  }, [apiBaseUrl, attempt, createSource, deps]);

  function reconnect() {
    setStatus("connecting");
    setAttempt((n) => n + 1);
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
        <p role="status" className="flex items-center gap-2 text-sm">
          <span
            data-slot="status-dot"
            data-state={status}
            aria-hidden="true"
            className={cn("size-2.5 shrink-0 rounded-full", DOT_CLASS[status])}
          />
          {STATUS_TEXT[status]}
        </p>
        {status === "closed" ? (
          <Button type="button" size="sm" onClick={reconnect}>
            Reconnect
          </Button>
        ) : null}
      </div>
      {articles.length === 0 && status !== "closed" ? (
        <EmptyState
          title="Waiting for new articles…"
          description="Stories show up here the moment they are processed."
        />
      ) : null}
      <ol className="flex flex-col gap-3">
        {articles.map((article) => (
          <ArticleItem
            key={article.article_id}
            article={article}
            className="motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-top-2"
          />
        ))}
      </ol>
    </section>
  );
}
