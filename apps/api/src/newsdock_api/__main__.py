"""Entrypoint for newsdock-api: wires config and starts the app."""

from newsdock_api.config import Settings


def main() -> int:
    settings = Settings()
    print(f"newsdock-api (log level {settings.log_level})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
