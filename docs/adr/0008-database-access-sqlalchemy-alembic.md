# ADR-0008: SQLAlchemy 2 for database access, Alembic for migrations

Status: **Accepted 2026-10-05** (user decision in `/spec-design foundation`, spec D-9). Replaces the first proposal (dbmate + psycopg), which assumed "no ORM"; no earlier document had decided the database library.

## Context
AC-11 needs an idempotent baseline migration. M1 needs queries with `ON CONFLICT DO NOTHING`, `text[]` with `@>`, `jsonb`, `ILIKE`, keyset pagination and, later, pgvector. The M1 design only said "parameterized SQL"; it did not name a library.

## Options
1. psycopg 3 + plain SQL + dbmate (v2.36.0, plain SQL files, empty `down` sections required **[verified]**).
2. SQLAlchemy 2 Core + dbmate (migrations stay plain SQL, table definitions kept in step by hand).
3. SQLAlchemy 2 + Alembic: SQLAlchemy 2.1.3, Alembic 1.20.0, psycopg 3.3.6 as the driver **[verified, PyPI 2026-10-05]**.

## Decision
Option 3, chosen by the user for the standard Python stack and portfolio value. Consequences for the layout:
- New shared package `packages/db` (`newsdock_db`): `config.py` (`DATABASE_URL` via pydantic-settings), engine factory, and the shared `MetaData`. Empty in M0 (no domain tables); M1 adds tables.
- Alembic project in `infra/migrations/` (`alembic.ini`, `env.py`, `versions/NNNN_<name>.py`, `Dockerfile`); revision ids are numeric (`0001`). `env.py` takes its URL from `newsdock_db.config`, not from `os.environ` (DR-9).
- `newsdock_core` and every `domain/` must not import `newsdock_db`, `sqlalchemy`, `alembic` or `psycopg`; only `adapters/` may (DR-6, DR-7).
- Core versus ORM-mapped classes is left to the M1 design; M0 only provides the metadata container.

## Consequences
+ Industry-standard stack, composable queries for optional search filters, one place for table definitions, migrations versioned in Python. − One more shared package and a migration image (not one of the six apps); schema defined in two ways if both `Table` objects and hand-written migrations are used (review discipline or autogenerate checks, decided in M1); the M1 docs must say which SQLAlchemy layer is used. dbmate and psycopg-only were rejected as simpler but less standard.
