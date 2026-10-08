"""Docker healthcheck: python -m newsdock_agent.adapters.healthcheck (ADR-0015)."""

from newsdock_config import load_settings
from newsdock_config.health import check_heartbeat

from newsdock_agent.config import Settings


def main() -> int:
    return check_heartbeat(load_settings(Settings).heartbeat_file)


if __name__ == "__main__":
    raise SystemExit(main())
