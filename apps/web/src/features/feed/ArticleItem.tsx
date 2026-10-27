// One article row, shared by the feed and the live page. All text is rendered by
// React (escaped, never HTML); no data fetching here.
import Link from "next/link";
import type { ArticleSummary } from "./api";

function ScoreBadge({ scores }: { scores: ArticleSummary["scores"] }) {
  if (!scores) return null;
  return (
    <span>
      {Object.entries(scores).map(([agent, score]) => (
        <em key={agent} title={agent}>
          {score.toFixed(2)}
        </em>
      ))}
    </span>
  );
}

export function ArticleItem({ article }: { article: ArticleSummary }) {
  return (
    <li>
      <Link href={`/articles/${article.article_id}`}>{article.title}</Link>{" "}
      <small>
        {article.domain ?? "unknown"} ·{" "}
        {new Date(article.published_at).toLocaleString()}
      </small>{" "}
      {article.source_count > 1 ? (
        <small>· {article.source_count} sites</small>
      ) : null}{" "}
      <ScoreBadge scores={article.scores ?? null} />
    </li>
  );
}
