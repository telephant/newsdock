"""Errors the agent tells apart."""


class Unauthorized(Exception):
    """The platform rejected the agent's key (HTTP 401): wrong, revoked or missing."""
