"""TC-22 (AC-15): the digest service has no data route but MCP, and its own key."""

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    loaded = yaml.safe_load((ROOT / "infra/compose.yaml").read_text())
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="module")
def digest(compose: dict[str, Any]) -> dict[str, Any]:
    service = compose["services"]["digest"]
    assert isinstance(service, dict)
    return service


def test_tc22_it_is_on_the_agent_network_only(digest: dict[str, Any]) -> None:
    assert digest["networks"] == ["agent"]


def test_tc22_it_has_no_database_or_kafka_settings(digest: dict[str, Any]) -> None:
    env = digest["environment"]
    for name in env:
        assert not name.startswith(("DATABASE", "KAFKA", "POSTGRES")), name
    assert "depends_on" in digest and list(digest["depends_on"]) == ["api"]


def test_tc22_it_uses_its_own_key_not_the_demo_agents(digest: dict[str, Any]) -> None:
    key = digest["environment"]["NEWSDOCK_AGENT_API_KEY"]
    assert "NEWSDOCK_DIGEST_API_KEY" in key
    assert "${NEWSDOCK_AGENT_API_KEY" not in key


def test_tc22_it_runs_the_agent_image_with_the_digest_command(
    compose: dict[str, Any], digest: dict[str, Any]
) -> None:
    agent = compose["services"]["agent"]
    assert digest["image"] == agent["image"] == "newsdock-agent:dev"
    assert digest["build"] == agent["build"]
    assert digest["command"] == ["python", "-m", "newsdock_agent.digest"]
    assert digest["profiles"] == ["apps"]


def test_it_mounts_the_output_folder_and_a_state_volume(
    compose: dict[str, Any], digest: dict[str, Any]
) -> None:
    assert "./digests:/digests" in digest["volumes"]  # infra/digests on the host
    assert "digest_state:/data" in digest["volumes"]
    assert "digest_state" in compose["volumes"]
    env = digest["environment"]
    assert env["NEWSDOCK_AGENT_DIGEST_DIR"] == "/digests"
    assert env["NEWSDOCK_AGENT_DIGEST_STATE_FILE"] == "/data/digest-baseline.json"


def test_it_uses_the_shared_heartbeat_healthcheck(digest: dict[str, Any]) -> None:
    test = digest["healthcheck"]["test"]
    assert "newsdock_agent.adapters.healthcheck" in " ".join(test)


def test_the_output_folder_is_git_ignored_and_the_key_is_in_the_env_example() -> None:
    assert "infra/digests/" in (ROOT / ".gitignore").read_text().splitlines()
    env_lines = (ROOT / ".env.example").read_text().splitlines()
    assert "NEWSDOCK_DIGEST_API_KEY=" in env_lines  # empty, never a real key


def test_make_digest_once_exists_and_is_listed_in_help() -> None:
    makefile = (ROOT / "Makefile").read_text()
    lines = makefile.splitlines()
    target = next((ln for ln in lines if ln.startswith("digest-once:")), "")
    assert "##" in target  # a description, so `make help` lists it
    phony = [ln for ln in lines if ln.startswith(".PHONY:")]
    assert any("digest-once" in ln.split() for ln in phony)
    assert "NEWSDOCK_DIGEST_API_KEY" in makefile


def test_the_isolation_scene_covers_the_digest_container() -> None:
    scene = (ROOT / "infra/scripts/tests/test_agent_isolation.py").read_text()
    assert "digest" in scene
