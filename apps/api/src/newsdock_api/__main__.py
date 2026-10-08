"""Entrypoint for newsdock-api: uvicorn serving MCP + REST in one process."""

import logging

import uvicorn
from newsdock_config import load_settings, log_effective_config

from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings


def main() -> int:
    settings = load_settings(Settings)
    logging.basicConfig(level=settings.log_level)
    log_effective_config(logging.getLogger(__name__), settings)
    logging.getLogger(__name__).info("newsdock-api starting on :%d", settings.port)
    if settings.uvicorn_workers > 1:  # several workers need an import string
        uvicorn.run(
            "newsdock_api.adapters.http:create_app",
            factory=True,
            workers=settings.uvicorn_workers,
            host=settings.host,
            port=settings.port,
            log_level=settings.uvicorn_log_level,
        )
    else:
        uvicorn.run(
            create_app(settings),
            host=settings.host,
            port=settings.port,
            log_level=settings.uvicorn_log_level,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
