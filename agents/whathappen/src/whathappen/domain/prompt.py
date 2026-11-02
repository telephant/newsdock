"""The per-group prompt (design-detail §5). Pure: no I/O.

It is built from one story group's headlines only: no counts, urls, labels or other
groups are ever passed in, so none can reach the model (AC-9). Python groups and
counts, the model writes one sentence.
"""

from collections.abc import Sequence

from whathappen.domain.titles import clean_title

_GROUP_TEMPLATE = (
    "Headlines:\n"
    "{titles}\n"
    "Write ONE plain sentence (at most 30 words) saying what these headlines "
    "report.\n"
    "Use only facts in the headlines. Do not add names, numbers or causes that "
    "are not there."
)


def group_prompt(titles: Sequence[str]) -> str:
    """The prompt for one story group: its headlines and nothing else (no label,
    counts, urls or other groups can reach the model)."""
    lines = [f"- {cleaned}" for t in titles if (cleaned := clean_title(t))]
    return _GROUP_TEMPLATE.format(titles="\n".join(lines))
