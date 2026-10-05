"""TC-35: the agent's config can only name the MCP and Ollama endpoints."""

import pytest
from newsdock_agent.config import Settings
from pydantic import ValidationError


def test_config_exposes_no_db_or_kafka_fields() -> None:
    field_names = set(Settings.model_fields)
    assert not {f for f in field_names if "database" in f or "kafka" in f or "dsn" in f}
    assert {"mcp_url", "ollama_url"} <= field_names


def test_unknown_settings_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://sneaky")
