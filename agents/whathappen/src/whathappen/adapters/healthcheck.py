"""Docker healthcheck: python -m whathappen.adapters.healthcheck."""

from whathappen.adapters.heartbeat import check_heartbeat
from whathappen.config import Settings


def main() -> int:
    return check_heartbeat(Settings().heartbeat_file)


if __name__ == "__main__":
    raise SystemExit(main())
