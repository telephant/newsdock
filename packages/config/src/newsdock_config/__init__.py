"""Layered configuration for newsdock services (ADR-0013)."""

from newsdock_config.errors import ConfigError
from newsdock_config.settings import (
    LayeredSettings,
    load_settings,
    log_effective_config,
)

__all__ = ["ConfigError", "LayeredSettings", "load_settings", "log_effective_config"]
