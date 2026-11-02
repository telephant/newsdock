"""The per-theme prompt (design-detail §5). Pure: no I/O.

It is built from a theme label and headlines only: no counts, urls or other themes
are ever passed in, so none can reach the model (AC-9). Python counts, the model
writes prose.
"""

from collections.abc import Sequence

from whathappen.domain.text import clean_text
from whathappen.domain.titles import clean_title

_TEMPLATE = (
    "Theme: {label}\n"
    "Headlines:\n"
    "{titles}\n"
    "Write ONE plain sentence (at most 30 words) saying what these headlines "
    "are about.\n"
    "Use only facts in the headlines. Do not add names, numbers or causes that "
    "are not there."
)


def theme_prompt(label: str, titles: Sequence[str]) -> str:
    lines = [f"- {cleaned}" for t in titles if (cleaned := clean_text(t))]
    return _TEMPLATE.format(label=clean_text(label), titles="\n".join(lines))


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
