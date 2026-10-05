"""Entrypoint for newsdock-sink: wires config and starts the app."""

from newsdock_sink.config import Settings


def main() -> int:
    settings = Settings()
    print(f"newsdock-sink (log level {settings.log_level})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
