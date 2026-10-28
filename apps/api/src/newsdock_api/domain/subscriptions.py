"""Subscription filters (spec D-2, D-7): AND of optional theme, domain and text.

Pure validation only; matching itself is SQL (`list_new`), so there is exactly one
implementation of the semantics. `theme` ending in `*` is a prefix match over any
of an article's themes; anything else is an exact theme. An empty filter matches
every article.
"""

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError, field_validator
from pydantic_core.core_schema import ValidationInfo

from newsdock_api.domain.agents import AgentScope

PREFIX_MARK = "*"


class InvalidFilter(ValueError):
    """The submitted filter is not valid (maps to HTTP 422)."""


class SubscriptionFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    theme: StrictStr | None = None
    domain: StrictStr | None = None
    text: StrictStr | None = None

    @field_validator("theme", "domain", "text")
    @classmethod
    def _non_empty_and_short(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("must not be empty")
        context = info.context or {}
        limit = context.get("max_length")
        if limit is not None and len(value) > limit:
            raise ValueError(f"longer than {limit} characters")
        return value

    @field_validator("theme")
    @classmethod
    def _star_only_as_a_suffix(cls, value: str | None) -> str | None:
        if value is None:
            return None
        body = value[:-1] if value.endswith(PREFIX_MARK) else value
        if PREFIX_MARK in body or not body:
            raise ValueError(
                "'*' is only allowed as the last character, after a prefix"
            )
        return value

    def as_query(self) -> dict[str, str | None]:
        """Arguments for `list_new` / `search` (None = no constraint)."""
        return {"theme": self.theme, "domain": self.domain, "text": self.text}

    def as_json(self) -> dict[str, str]:
        """Storage form: only the fields that were given."""
        return {k: v for k, v in self.as_query().items() if v is not None}


def parse_filter(raw: Any, max_length: int) -> SubscriptionFilter:
    if not isinstance(raw, dict):
        raise InvalidFilter("filter must be an object")
    try:
        return SubscriptionFilter.model_validate(
            raw, context={"max_length": max_length}
        )
    except ValidationError as exc:
        raise InvalidFilter(str(exc)) from exc


def split_theme(theme: str) -> tuple[str, bool]:
    """(value, is_prefix): `ECON_*` gives (`ECON_`, True); `ECON_X` is exact."""
    if theme.endswith(PREFIX_MARK):
        return theme[:-1], True
    return theme, False


class SubscriptionRecord(BaseModel):
    id: str
    agent_id: str
    filter: dict[str, str]
    created_at: datetime


class AdminSubscription(SubscriptionRecord):
    agent_name: str


class SubscriptionStore(Protocol):
    """Persistence the routes and the stream need (SqlSubscriptionsRepo)."""

    def create(
        self, agent_id: str, filter_json: dict[str, str]
    ) -> SubscriptionRecord: ...

    def list_own(self, agent_id: str) -> list[SubscriptionRecord]: ...

    def get_own(self, agent_id: str, sub_id: str) -> SubscriptionRecord | None: ...

    def delete_own(self, agent_id: str, sub_id: str) -> bool: ...

    def count_own(self, agent_id: str) -> int: ...

    def exists(self, sub_id: str) -> bool: ...

    def delete_visible(self, sub_id: str, scope: AgentScope) -> bool:
        """Delete a subscription of an agent the scope may see; False if absent
        or not visible (ADR-0023)."""
        ...

    def list_visible(self, scope: AgentScope) -> list[AdminSubscription]: ...
