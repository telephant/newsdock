# newsdock-db

Shared database package (`newsdock_db`, ADR-0008): `config.py` (`DATABASE_URL`), `engine.py` (sync and async SQLAlchemy engine factories) and `metadata.py` (the shared `MetaData`, empty in M0). Only `adapters/` code and the Alembic project in `infra/migrations/` may import it; `domain/` and `newsdock_core` never do (rules DR-6, DR-7).

Test: `uv run pytest packages/db`. Migrations: `make migrate`.
