"""Docker healthcheck: python -m newsdock_api.adapters.healthcheck (ADR-0015)."""

from newsdock_config import load_settings
from newsdock_config.health import check_http

from newsdock_api.config import Settings

HEALTH_TIMEOUT_SECONDS = 3.0


def main() -> int:
    settings = load_settings(Settings)
    return check_http(
        f"http://localhost:{settings.port}/api/health",
        timeout_seconds=HEALTH_TIMEOUT_SECONDS,
    )


if __name__ == "__main__":
    raise SystemExit(main())
