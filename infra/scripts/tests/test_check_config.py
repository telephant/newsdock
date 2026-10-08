"""TC-14 (+ TC-4 committed-file half): the config check on real and synthetic trees."""

from pathlib import Path

import check_config

ROOT = Path(__file__).resolve().parents[3]

GOOD_YAML = """\
common:
  log_level: INFO
  kafka:
    topics: {raw: gkg.raw}
ingester:
  max_attempts: 4
web:
  poll_ms: 60000
"""


def tree(
    tmp_path: Path, yaml_text: str = GOOD_YAML, files: dict[str, str] | None = None
) -> Path:
    config = tmp_path / "infra" / "config"
    config.mkdir(parents=True)
    (config / "newsdock.yaml").write_text(yaml_text)
    for rel, code in (files or {}).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code)
    return tmp_path


def messages(root: Path) -> str:
    return "\n".join(str(v) for v in check_config.check(root))


def test_the_real_tree_passes() -> None:
    assert check_config.check(ROOT) == []


def test_a_clean_synthetic_tree_passes(tmp_path: Path) -> None:
    assert check_config.check(tree(tmp_path)) == []


def test_unknown_service_key_is_reported_with_section_and_key(tmp_path: Path) -> None:
    text = messages(tree(tmp_path, GOOD_YAML + "sink:\n  batchsize: 3\n"))
    assert "sink.batchsize" in text


def test_common_key_known_to_no_service_is_reported(tmp_path: Path) -> None:
    text = messages(tree(tmp_path, GOOD_YAML.replace("INFO", "INFO\n  nobody: 1")))
    assert "common.nobody" in text


def test_secret_key_is_reported(tmp_path: Path) -> None:
    text = messages(tree(tmp_path, GOOD_YAML + "api:\n  admin_password: x\n"))
    assert "admin_password" in text


def test_value_different_from_the_default_is_reported(tmp_path: Path) -> None:
    text = messages(
        tree(tmp_path, GOOD_YAML.replace("max_attempts: 4", "max_attempts: 9"))
    )
    assert "ingester.max_attempts" in text and "default" in text


def test_unknown_web_key_is_reported(tmp_path: Path) -> None:
    text = messages(tree(tmp_path, GOOD_YAML + "  colour: red\n"))
    assert "web.colour" in text


def test_topic_literal_in_app_code_is_reported(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        files={"apps/sink/src/newsdock_sink/adapters/x.py": "TOPIC = 'gkg.clean'\n"},
    )
    text = messages(root)
    assert "gkg.clean" in text and "adapters/x.py" in text


def test_constant_name_in_app_code_is_reported(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        files={"apps/ingester/src/newsdock_ingester/domain/y.py": "MAX_ATTEMPTS = 4\n"},
    )
    assert "MAX_ATTEMPTS" in messages(root)


def test_literals_in_config_py_docstrings_and_tests_are_allowed(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        files={
            "apps/sink/src/newsdock_sink/config.py": (
                "x = 'gkg.clean'\nMAX_ATTEMPTS = 4\n"
            ),
            "apps/sink/src/newsdock_sink/adapters/doc.py": '"""Reads gkg.clean."""\n',
            "apps/sink/tests/unit/test_a.py": "TOPIC = 'gkg.clean'\n",
        },
    )
    assert check_config.check(root) == []


def test_web_poll_constant_is_reported(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        files={"apps/web/src/features/f.ts": "const POLL_MS = 60000;\n"},
    )
    assert "POLL_MS" in messages(root)
