"""The article shape the digest works with (a subset of the MCP article summary)."""

from collections.abc import Mapping
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class Article(BaseModel):
    model_config = ConfigDict(frozen=True)

    article_id: str
    title: str
    url: str
    domain: str | None = None
    published_at: datetime
    themes: list[str] = []
    source_count: int = 1
    # GDELT's negative-tone share; absent when the platform does not return it yet
    # (the digest then ranks by coverage alone) and null when the article has none.
    tone_neg: float | None = None

    @field_validator("themes", mode="before")
    @classmethod
    def _no_themes_is_empty(cls, value: object) -> object:
        return [] if value is None else value

    @classmethod
    def from_mcp(cls, raw: Mapping[str, object]) -> "Article":
        return cls.model_validate(raw)
