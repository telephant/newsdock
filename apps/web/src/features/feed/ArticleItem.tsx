// One article card, shared by the feed and the live page. All text is rendered by
// React (escaped, never HTML); no data fetching here.
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { ArticleSummary } from "./api";
import { timeAgo } from "./time";

function ScoreBadges({ scores }: { scores: ArticleSummary["scores"] }) {
  if (!scores) return null;
  return (
    <>
      {Object.entries(scores).map(([agent, score]) => (
        <Badge key={agent} variant="outline" title={agent}>
          {score.toFixed(2)}
        </Badge>
      ))}
    </>
  );
}

export function ArticleItem({ article }: { article: ArticleSummary }) {
  return (
    <li>
      <Card className="min-w-0 py-4 transition-colors hover:bg-muted/40">
        <CardContent className="flex min-w-0 flex-col gap-2 px-4">
          <Link
            href={`/articles/${article.article_id}`}
            className="line-clamp-3 min-w-0 text-base leading-snug font-medium break-words underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            {article.title}
          </Link>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            <span className="break-all">{article.domain ?? "unknown"}</span>
            <span aria-hidden>·</span>
            <time
              dateTime={article.published_at}
              title={new Date(article.published_at).toLocaleString()}
            >
              {timeAgo(article.published_at)}
            </time>
            {article.source_count > 1 ? (
              <Badge variant="secondary">{article.source_count} sites</Badge>
            ) : null}
            <ScoreBadges scores={article.scores ?? null} />
          </div>
        </CardContent>
      </Card>
    </li>
  );
}
