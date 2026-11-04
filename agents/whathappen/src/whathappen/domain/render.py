"""Markdown rendering of one digest (spec §5, design-detail §5). Pure: no I/O.

Layout: a marker line, one `#` heading, a two-line notice, a "Top stories" block and
then one `##` section per label. Everything that came from the data or the model is
cleaned and escaped as markdown text, so no markup or HTML is produced.
"""

from collections.abc import Mapping
from datetime import datetime

from whathappen.domain.articles import Article
from whathappen.domain.scoring import RANKING_TONE, ScoredGroup
from whathappen.domain.sections import Selection
from whathappen.domain.text import clean_text, encode_url, escape_markdown, escape_text
from whathappen.domain.titles import clean_title

# The first line of every digest. It is invisible when rendered and lets the cleanup
# command tell a new file from one written by the old theme digest.
MARKER = "<!-- whathappen:story-first -->"
_NOTICE_FIRST = (
    "> New this hour, from headlines only. Ranked by outlets covering a story"
)
_NOTICE_FIRST_GROUNDED = (
    "> New this hour, from headlines and stored article text. "
    "Ranked by outlets covering a story"
)
_NOTICE_SECOND = (
    "> Summaries are written by a small local model and can be wrong; open the links."
)


def _count(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _link(article: Article) -> str:
    title = escape_markdown(clean_title(article.title)) or escape_text(article.url)
    return f"[{title}]({encode_url(article.url)})"


def _story_line(prefix: str, item: ScoredGroup) -> str:
    shown = item.group.shown
    parts = [f"{prefix}{_link(shown)}"]
    if shown.domain:
        parts.append(escape_text(shown.domain))
    parts.append(_count(item.sources, "source", "sources"))
    return " · ".join(parts)


def _story(
    prefix: str,
    indent: str,
    item: ScoredGroup,
    summaries: Mapping[str, str | None],
    also_limit: int,
) -> list[str]:
    group = item.group
    lines = [_story_line(prefix, item)]
    summary = summaries.get(group.key)  # the cycle decides which groups get one
    if summary and clean_text(summary):
        lines.append(indent + escape_text(summary))
    also = group.also[:also_limit]
    if also:
        lines.append(indent + "Also: " + ", ".join(_link(a) for a in also))
    return lines


def render_story_digest(
    *,
    now: datetime,
    article_count: int,
    selection: Selection,
    ranking: str,
    summaries: Mapping[str, str | None],
    min_sources: int,
    also_limit: int,
    body_grounded: bool = False,
) -> str:
    """The whole file: marker, heading, notice, Top stories, labelled sections."""
    listed = len(selection.top) + sum(len(s.groups) for s in selection.sections)
    how = "." if ranking != RANKING_TONE else " and negative tone."
    first = _NOTICE_FIRST_GROUNDED if body_grounded else _NOTICE_FIRST
    lines = [
        MARKER,
        f"# What happened · {now:%Y-%m-%d %H:%M} UTC "
        f"({_count(article_count, 'new article', 'new articles')} · "
        f"{_count(listed, 'story', 'stories')})",
        "",
        first + how,
        _NOTICE_SECOND,
    ]
    if listed == 0:
        lines += [
            "",
            f"No story was carried by {min_sources} or more outlets this hour.",
        ]
        return "\n".join(lines) + "\n"
    if selection.top:
        lines += ["", "## Top stories"]
        for number, item in enumerate(selection.top, start=1):
            lines += _story(f"{number}. ", "   ", item, summaries, also_limit)
    for section in selection.sections:
        lines += ["", f"## {clean_text(section.label)}"]  # operator config, not data
        for item in section.groups:
            lines += _story("- ", "  ", item, summaries, also_limit)
    return "\n".join(lines) + "\n"
