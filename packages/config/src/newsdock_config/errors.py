"""Errors raised while resolving configuration."""


class ConfigError(Exception):
    """The configuration is unusable; the message names the file, section and key."""
