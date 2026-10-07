"use client";
// Article detail (AC-12): fields + analyses. payload.reason is plain text —
// React escapes it; never use dangerouslySetInnerHTML here (security §6).
import { useEffect, useState } from "react";
import { fetchArticle, type ArticleDetail } from "../feed/api";

export function Detail({ articleId }: { articleId: string }) {
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchArticle(articleId).then(setArticle, (e) => setError(String(e)));
  }, [articleId]);

  if (error) return <p role="alert">{error}</p>;
  if (!article) return <p>Loading…</p>;

  return (
    <article>
      <h1>{article.title}</h1>
      <p>
        <a href={article.url} rel="noreferrer noopener">
          {article.url}
        </a>
      </p>
      <dl>
        <dt>Domain</dt>
        <dd>{article.domain ?? "unknown"}</dd>
        <dt>Published</dt>
        <dd>{new Date(article.published_at).toLocaleString()}</dd>
        <dt>Slot</dt>
        <dd>{article.slot}</dd>
        <dt>Themes</dt>
        <dd>{article.themes.join(", ") || "none"}</dd>
        <dt>Tone</dt>
        <dd>{article.tone ?? "n/a"}</dd>
      </dl>
      <h2>Seen on {article.source_count} sites</h2>
      <ul>
        {article.sources.map((source) => (
          <li key={source.url}>
            <strong>{source.domain ?? "unknown"}</strong> —{" "}
            <a href={source.url} rel="noreferrer noopener">
              {source.url}
            </a>{" "}
            <small>{new Date(source.published_at).toLocaleString()}</small>
          </li>
        ))}
      </ul>
      <h2>Agent analyses</h2>
      {article.analyses.length === 0 ? <p>None yet.</p> : null}
      <ul>
        {article.analyses.map((analysis) => (
          <li key={analysis.agent_name}>
            <strong>{analysis.agent_name}</strong>:{" "}
            {JSON.stringify(analysis.payload)}{" "}
            <small>{new Date(analysis.created_at).toLocaleString()}</small>
          </li>
        ))}
      </ul>
    </article>
  );
}
