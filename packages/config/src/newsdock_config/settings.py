"""LayeredSettings: env > YAML file (common + service section) > code defaults."""

import logging
import sys
from typing import Any, ClassVar, TypeVar

from pydantic import ValidationError
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from newsdock_config.errors import ConfigError
from newsdock_config.secrets import is_secret_name
from newsdock_config.source import FileSource


class LayeredSettings(BaseSettings):
    """Base for every service's Settings. Subclasses set `section` and `env_prefix`."""

    model_config = SettingsConfigDict(extra="forbid", populate_by_name=True)

    section: ClassVar[str] = ""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            FileSource(settings_cls, cls.section, env_settings),
        )

    def redacted(self) -> dict[str, Any]:
        """Effective values for the startup log; secret-looking names are masked."""
        return {
            name: "***" if is_secret_name(name) else value
            for name, value in self.model_dump().items()
        }


S = TypeVar("S", bound=LayeredSettings)


def load_settings(settings_cls: type[S]) -> S:
    """Build settings; on a bad config print one clear line to stderr and exit 2."""
    try:
        return settings_cls()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        print(f"config error: {settings_cls.section}: {problems}", file=sys.stderr)
        raise SystemExit(2) from exc


def log_effective_config(logger: logging.Logger, settings: LayeredSettings) -> None:
    """One INFO line with the effective, redacted settings (spec NFR)."""
    shown = " ".join(f"{k}={v}" for k, v in sorted(settings.redacted().items()))
    logger.info("effective config [%s]: %s", settings.section, shown)
