"""Entrypoint for newsdock-ingester: wires config and starts the app."""

from newsdock_ingester.config import Settings


def main() -> int:
    settings = Settings()
    print(f"newsdock-ingester (log level {settings.log_level})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
