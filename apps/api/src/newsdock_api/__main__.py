"""Entrypoint for newsdock-api: uvicorn serving MCP + REST in one process."""

import logging

import uvicorn

from newsdock_api.adapters.http import create_app
from newsdock_api.config import Settings


def main() -> int:
    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    logging.getLogger(__name__).info("newsdock-api starting on :%d", settings.port)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
