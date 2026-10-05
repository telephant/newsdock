"""Rule tests (marker `rules`): each enforced rule fails when violated (AC-5/7/17)."""

import pytest

from .conftest import output, run, temp_module

pytestmark = pytest.mark.rules

APPS = ["ingester", "processor", "sink", "api", "agent"]


def test_type_error_fails_and_names_the_app() -> None:  # TC-10
    source = 'def broken() -> int:\n    return "x"\n'
    with temp_module("apps/sink/src/newsdock_sink", source) as path:
        result = run("make", "check-python")
    text = output(result)
    assert result.returncode != 0
    assert path.name in text
    assert "newsdock_sink" in text


def test_app_importing_another_app_fails() -> None:  # TC-14
    with temp_module("apps/api/src/newsdock_api/adapters", "import newsdock_sink\n"):
        result = run("make", "imports-python")
    text = output(result)
    assert result.returncode != 0
    assert "DR-7 apps are independent" in text
    assert "newsdock_api" in text and "newsdock_sink" in text


def test_app_importing_core_is_allowed() -> None:  # TC-15, negative control
    with temp_module("apps/api/src/newsdock_api/adapters", "import newsdock_core\n"):
        result = run("make", "imports-python")
    assert result.returncode == 0, output(result)


@pytest.mark.parametrize(
    "statement",
    [
        "import httpx",
        "import sqlalchemy",
        "import newsdock_db",
        "import newsdock_processor.adapters",
    ],
)
def test_domain_must_stay_pure(statement: str) -> None:  # TC-42
    with temp_module("apps/processor/src/newsdock_processor/domain", statement + "\n"):
        result = run("make", "imports-python")
    text = output(result)
    assert result.returncode != 0
    assert "DR-6 domain is pure" in text
    assert "newsdock_processor.domain" in text


@pytest.mark.parametrize(
    "statement", ["import newsdock_api", "import newsdock_db", "import sqlalchemy"]
)
def test_core_must_stay_clean(statement: str) -> None:  # TC-43
    with temp_module("packages/core/src/newsdock_core", statement + "\n"):
        result = run("make", "imports-python")
    text = output(result)
    assert result.returncode != 0
    assert "DR-7 core imports no app, db or I/O library" in text
    assert "newsdock_core" in text


@pytest.mark.parametrize(
    "source",
    [
        'import os\n\nVALUE = os.environ["X"]\n',
        'import os\n\nVALUE = os.getenv("X")\n',
    ],
)
def test_env_is_read_only_in_config_py(source: str) -> None:  # TC-44
    with temp_module("apps/ingester/src/newsdock_ingester/adapters", source):
        result = run("make", "lint-python")
    text = output(result)
    assert result.returncode != 0
    assert "DR-9" in text


def test_env_reads_inside_config_py_are_allowed() -> None:  # TC-44, negative control
    source = 'import os\n\nVALUE = os.environ["X"]\n'
    with temp_module("apps/ingester/src/newsdock_ingester", source, name="config.py"):
        result = run("make", "lint-python")
    assert result.returncode == 0, output(result)
