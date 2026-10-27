"use client";
// Article detail (AC-12): fields + analyses. payload.reason is plain text —
// React escapes it; never render agent or source text as HTML (security §6).
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { useRuntimeConfig } from "@/components/ConfigProvider";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ListSkeleton } from "@/components/ListSkeleton";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchArticle, type ArticleDetail } from "../feed/api";

const linkClass =
  "inline-flex min-w-0 items-center gap-1 text-primary-text underline underline-offset-4 break-all hover:no-underline focus-visible:rounded-sm focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </dt>
      <dd className="mt-0.5 break-words">{children}</dd>
    </div>
  );
}

export function Detail({ articleId }: { articleId: string }) {
  const { apiBaseUrl } = useRuntimeConfig();
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchArticle({ apiBaseUrl }, articleId).then(setArticle, (e) =>
      setError(String(e)),
    );
  }, [apiBaseUrl, articleId]);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <Link href="/" className={`${linkClass} self-start no-underline`}>
        <ArrowLeft aria-hidden className="size-4" />
        Back to feed
      </Link>
      {error ? <ErrorAlert message={error} /> : null}
      {!article && !error ? <ListSkeleton rows={2} /> : null}
      {article ? <Body article={article} /> : null}
    </div>
  );
}

function Body({ article }: { article: ArticleDetail }) {
  return (
    <article className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl leading-snug font-semibold tracking-tight break-words">
          {article.title}
        </h1>
        <a href={article.url} rel="noreferrer noopener" className={linkClass}>
          {article.url}
          <ExternalLink aria-hidden className="size-3.5 shrink-0" />
        </a>
      </header>

      <Card>
        <CardContent>
          <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
            <Field label="Domain">{article.domain ?? "unknown"}</Field>
            <Field label="Published">
              {new Date(article.published_at).toLocaleString()}
            </Field>
            <Field label="Slot">{article.slot}</Field>
            <Field label="Tone">{article.tone ?? "n/a"}</Field>
            <div className="sm:col-span-2">
              <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Themes
              </dt>
              <dd className="mt-1 flex flex-wrap gap-1.5">
                {article.themes.length === 0 ? (
                  <span className="text-muted-foreground">none</span>
                ) : (
                  article.themes.map((theme) => (
                    <Badge key={theme} variant="secondary">
                      {theme}
                    </Badge>
                  ))
                )}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">
          Seen on {article.source_count} sites
        </h2>
        <ul className="divide-y divide-border rounded-xl border border-border bg-card">
          {article.sources.map((source) => (
            <li key={source.url} className="flex flex-col gap-1 px-4 py-3">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                <strong className="font-medium">
                  {source.domain ?? "unknown"}
                </strong>
                <time
                  dateTime={source.published_at}
                  className="text-sm text-muted-foreground"
                >
                  {new Date(source.published_at).toLocaleString()}
                </time>
              </div>
              <a
                href={source.url}
                rel="noreferrer noopener"
                className={`${linkClass} text-sm`}
              >
                {source.url}
              </a>
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Agent analyses</h2>
        {article.analyses.length === 0 ? (
          <p className="text-muted-foreground">None yet.</p>
        ) : null}
        <ul className="flex flex-col gap-3">
          {article.analyses.map((analysis) => (
            <li key={analysis.agent_name}>
              <Card>
                <CardHeader>
                  <CardTitle>{analysis.agent_name}</CardTitle>
                  <time
                    dateTime={analysis.created_at}
                    className="text-sm text-muted-foreground"
                  >
                    {new Date(analysis.created_at).toLocaleString()}
                  </time>
                </CardHeader>
                <CardContent>
                  <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs leading-relaxed whitespace-pre-wrap break-words">
                    {JSON.stringify(analysis.payload, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}
