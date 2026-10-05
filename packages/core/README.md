# newsdock-core

Shared pure Python package (`newsdock_core`): GKG parsing, URL normalisation, domain models and the Kafka and analysis contracts (`contracts/`). It imports no app, no `newsdock_db` and no I/O library (rule DR-7). Empty subpackages in M0; M1 fills them.

Test: `uv run pytest packages/core`.
