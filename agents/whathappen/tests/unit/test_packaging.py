"""AC-15: this is an independent server. It shares no code and no docker network with
the platform, keeps its secrets in its own .env, and reaches newsdock only over HTTP."""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from whathappen.config import PROJECT_ROOT

ROOT: Path = PROJECT_ROOT


@pytest.fixture(scope="module")
def service() -> dict[str, Any]:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert list(compose["services"]) == ["whathappen"]
    assert isinstance(compose["services"]["whathappen"], dict)
    return compose["services"]["whathappen"]


def test_no_source_or_test_imports_platform_code() -> None:
    pattern = re.compile(r"^\s*(from|import)\s+(newsdock|apps|packages)\b", re.M)
    offenders = [
        str(path.relative_to(ROOT))
        for path in [
            *ROOT.joinpath("src").rglob("*.py"),
            *ROOT.joinpath("tests").rglob("*.py"),
        ]
        if pattern.search(path.read_text())
    ]
    assert offenders == []


def test_no_dependency_on_the_platform_workspace() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = project["project"]["dependencies"]
    assert not [d for d in dependencies if "newsdock" in d.lower()]
    assert "workspace" not in str(project.get("tool", {}).get("uv", {}))


def test_the_compose_service_joins_no_platform_network_and_needs_no_platform_service(
    service: dict[str, Any],
) -> None:
    assert "networks" not in service  # only its own default network
    assert "depends_on" not in service


def test_the_compose_service_has_no_database_or_kafka_settings(
    service: dict[str, Any],
) -> None:
    for name in service["environment"]:
        assert not name.startswith(("DATABASE", "KAFKA", "POSTGRES")), name


def test_the_container_reaches_the_host_not_loopback(service: dict[str, Any]) -> None:
    env = service["environment"]
    # The platform's MCP answers 421 to any Host header outside its allow-list
    # (localhost, 127.0.0.1, api), so the host is reached under the name "api".
    assert "http://api:8000/mcp" in env["WHATHAPPEN_MCP_URL"]
    assert "host.docker.internal:11434" in env["WHATHAPPEN_OLLAMA_URL"]
    assert "api:host-gateway" in service["extra_hosts"]
    assert "host.docker.internal:host-gateway" in service["extra_hosts"]


def test_secrets_come_from_the_projects_own_optional_dotenv(
    service: dict[str, Any],
) -> None:
    assert service["env_file"] == [{"path": ".env", "required": False}]
    assert "WHATHAPPEN_API_KEY" not in service["environment"]  # never inline


def test_output_is_a_host_visible_folder_and_the_health_check_is_its_own(
    service: dict[str, Any],
) -> None:
    assert "./output:/output" in service["volumes"]
    assert service["environment"]["WHATHAPPEN_OUTPUT_DIR"] == "/output"
    assert "whathappen.adapters.healthcheck" in " ".join(service["healthcheck"]["test"])


def test_env_example_has_an_empty_key_and_no_real_secret() -> None:
    lines = (ROOT / ".env.example").read_text().splitlines()
    assert "WHATHAPPEN_API_KEY=" in lines
    assert "ndk_" not in "\n".join(lines)


def test_env_and_output_are_git_ignored_in_the_project() -> None:
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in lines and "output/" in lines
    assert ".env" in (ROOT / ".dockerignore").read_text().splitlines()


def test_the_dockerfile_needs_only_this_folder() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "../" not in dockerfile
    assert "newsdock" not in dockerfile.lower()
    assert 'CMD ["python", "-m", "whathappen"]' in dockerfile


def test_the_makefile_has_the_documented_targets() -> None:
    makefile = (ROOT / "Makefile").read_text()
    for target in ("once", "run", "up", "down", "logs", "check", "test"):
        assert re.search(rf"^{target}:.*##", makefile, re.M), target
