"""Print the OpenAPI schema (consumed by apps/web type generation, T-10)."""

import json

from newsdock_api.adapters.http import create_app


def main() -> int:
    print(json.dumps(create_app().openapi(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
