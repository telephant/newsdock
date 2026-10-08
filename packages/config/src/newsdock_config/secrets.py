"""Secret-looking key names: allowed in env, never in the committed file (spec D-4)."""

import re
from collections.abc import Mapping
from typing import Any

from newsdock_config.errors import ConfigError

SECRET_KEY_PATTERN = re.compile(
    r"password|passwd|secret|token|dsn|credential|api_?key|database_url", re.IGNORECASE
)


def is_secret_name(name: str) -> bool:
    return SECRET_KEY_PATTERN.search(name) is not None


def check_no_secrets(raw: Mapping[str, Any], path: str, prefix: str = "") -> None:
    """Raise ConfigError naming the first secret-looking key at any nesting depth."""
    for key, value in raw.items():
        dotted = f"{prefix}{key}"
        if is_secret_name(str(key)):
            raise ConfigError(
                f"{path}: secret-looking key '{dotted}' is not allowed in the config "
                "file; set it through the environment instead"
            )
        if isinstance(value, Mapping):
            check_no_secrets(value, path, f"{dotted}.")
