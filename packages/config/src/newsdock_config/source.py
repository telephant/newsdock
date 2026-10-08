"""YAML settings source: `common:` merged under the service section."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from newsdock_config.errors import ConfigError
from newsdock_config.secrets import check_no_secrets


class _Location(BaseSettings):
    """Where the file is: `NEWSDOCK_CONFIG_FILE` (unset means no file layer)."""

    model_config = SettingsConfigDict(env_prefix="NEWSDOCK_", extra="ignore")

    config_file: str | None = None


def flatten(raw: Mapping[str, Any]) -> dict[str, tuple[Any, str]]:
    """Flatten nested keys: kafka.topics.clean -> kafka_topics_clean (value, dotted)."""
    out: dict[str, tuple[Any, str]] = {}

    def walk(node: Mapping[str, Any], names: list[str]) -> None:
        for key, value in node.items():
            path = [*names, str(key)]
            if isinstance(value, Mapping):
                walk(value, path)
            else:
                out["_".join(path)] = (value, ".".join(path))

    walk(raw, [])
    return out


def load_file(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    try:
        text = path.read_text()
    except OSError as exc:
        raise ConfigError(f"config file not readable: {path} ({exc.strerror})") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping of sections")
    check_no_secrets(raw, str(path))
    return raw


def _names(field_name: str, info: FieldInfo) -> set[str]:
    names = {field_name}
    alias = info.validation_alias
    if isinstance(alias, str):
        names.add(alias)
    elif alias is not None and hasattr(alias, "choices"):
        names.update(c for c in alias.choices if isinstance(c, str))
    return names


class FileSource(PydanticBaseSettingsSource):
    def __init__(
        self,
        settings_cls: type[BaseSettings],
        section: str,
        env_source: PydanticBaseSettingsSource,
    ) -> None:
        super().__init__(settings_cls)
        self._section = section
        self._env_source = env_source

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        return None, field_name, False  # unused: __call__ builds the whole mapping

    def __call__(self) -> dict[str, Any]:
        location = _Location().config_file
        if not location:
            return {}
        raw = load_file(location)
        fields = self.settings_cls.model_fields

        common = {
            name: value
            for name, (value, _) in flatten(raw.get("common") or {}).items()
            if name in fields
        }
        section: dict[str, Any] = {}
        for name, (value, dotted) in flatten(raw.get(self._section) or {}).items():
            if name not in fields:
                raise ConfigError(
                    f"{location}: '{self._section}.{dotted}' is not a setting of "
                    f"{self._section}"
                )
            section[name] = value
        merged = {**common, **section}

        supplied = set(self._env_source())
        return {
            name: value
            for name, value in merged.items()
            if not (_names(name, fields[name]) & supplied)
        }
