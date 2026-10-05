"""Entrypoint for newsdock-agent: wires config and starts the app."""

from newsdock_agent.config import Settings


def main() -> int:
    settings = Settings()
    print(f"newsdock-agent (log level {settings.log_level})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
