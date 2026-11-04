"""TC-20 (AC-15): the committed OpenAPI document is what the app generates, and it
shows the tone arguments and fields. The web types are generated from that file."""

import json
from pathlib import Path
from typing import Any

import pytest
from newsdock_api.adapters.http import create_app

ROOT = Path(__file__).resolve().parents[4]
COMMITTED = ROOT / "apps" / "web" / "src" / "lib" / "api" / "openapi.json"
TONE = {"tone", "tone_pos", "tone_neg", "tone_polarity"}


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@localhost:5/x")
    monkeypatch.delenv("NEWSDOCK_ADMIN_TOKEN", raising=False)


@pytest.fixture()
def generated() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(json.dumps(create_app().openapi()))
    return document


def test_the_committed_document_is_what_the_app_generates(
    generated: dict[str, Any],
) -> None:
    committed = json.loads(COMMITTED.read_text())
    assert committed == generated, (
        "apps/web/src/lib/api/openapi.json is stale: regenerate it "
        "(see docs/specs/tone-in-summary/tasks/T-09.md) and run generate:api"
    )


def test_the_feed_documents_the_two_new_parameters(generated: dict[str, Any]) -> None:
    params = {
        p["name"]: p for p in generated["paths"]["/api/articles"]["get"]["parameters"]
    }
    assert {"include", "min_negativity"} <= set(params)
    assert params["min_negativity"]["required"] is False
    assert params["include"]["required"] is False


def test_the_feed_schema_lists_the_optional_tone_keys(
    generated: dict[str, Any],
) -> None:
    ok = generated["paths"]["/api/articles"]["get"]["responses"]["200"]
    ref = ok["content"]["application/json"]["schema"]["$ref"]
    page = generated["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    item_ref = page["properties"]["articles"]["items"]["$ref"]
    item = generated["components"]["schemas"][item_ref.rsplit("/", 1)[-1]]
    assert TONE <= set(item["properties"])
    assert not TONE & set(item.get("required", []))  # optional, never required
    assert "seq" not in item["properties"]  # the raw cursor basis stays hidden


def test_the_detail_schema_has_all_four_tone_numbers(
    generated: dict[str, Any],
) -> None:
    detail = generated["components"]["schemas"]["ArticleDetail"]
    assert TONE <= set(detail["properties"])


# events-mentions TC-21 (AC-10, AC-11): the optional `events` key is documented
def test_the_feed_schema_lists_events_as_an_optional_key(
    generated: dict[str, Any],
) -> None:
    ok = generated["paths"]["/api/articles"]["get"]["responses"]["200"]
    ref = ok["content"]["application/json"]["schema"]["$ref"]
    page = generated["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    item_ref = page["properties"]["articles"]["items"]["$ref"]
    item = generated["components"]["schemas"][item_ref.rsplit("/", 1)[-1]]
    assert "events" in item["properties"]
    assert "events" not in item.get("required", [])  # optional, never required
    assert TONE <= set(item["properties"])  # the tone keys stay documented


def test_the_event_schema_has_the_curated_fields(generated: dict[str, Any]) -> None:
    schemas = generated["components"]["schemas"]
    event = schemas["EventOut"]
    assert {
        "event_id", "date", "cameo_code", "cameo_root", "goldstein", "quad_class",
        "num_mentions", "num_sources", "avg_tone", "actor1", "actor2", "location",
        "source_url", "mention_count",
    } == set(event["properties"])  # fmt: skip
    assert {"code", "name", "country", "type"} == set(
        schemas["EventActor"]["properties"]
    )
    assert {"name", "country", "adm1", "lat", "lon"} == set(
        schemas["EventLocation"]["properties"]
    )


def test_the_detail_schema_always_has_events(generated: dict[str, Any]) -> None:
    detail = generated["components"]["schemas"]["ArticleDetail"]
    assert "events" in detail["properties"]
    # always sent (the integration tests prove it); the schema gives it a default of [],
    # which the web type generator turns into a required property
    assert detail["properties"]["events"].get("default") == []


def test_the_detail_schema_documents_body_and_status(generated: dict[str, Any]) -> None:
    """TC-31 (body-extraction AC-9, AC-10)."""
    schemas = generated["components"]["schemas"]
    assert {"body", "body_status"} <= set(schemas["ArticleDetail"]["properties"])
    assert "body" in schemas["ArticleSummaryEvents"]["properties"]
