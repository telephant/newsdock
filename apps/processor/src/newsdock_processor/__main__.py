"""Entrypoint for newsdock-processor: wires config and starts the app."""

from newsdock_processor.config import Settings


def main() -> int:
    settings = Settings()
    print(f"newsdock-processor (log level {settings.log_level})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
