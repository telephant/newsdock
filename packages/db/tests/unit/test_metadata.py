"""The shared MetaData carries the M1 tables and a naming convention.

M0 asserted an empty MetaData; since T-03 (2026-10-05) the models module
registers the three M1 tables on import (ADR-0008).
"""

import newsdock_db.models  # noqa: F401  (registers the tables)
from newsdock_db.metadata import NAMING_CONVENTION, metadata


def test_metadata_holds_exactly_the_known_tables() -> None:
    # M1 tables + article_sources (M2a dedup-syndication, 2026-10-05)
    assert set(metadata.tables) == {
        "articles",
        "analyses",
        "ingest_slot",
        "article_sources",
    }


def test_naming_convention_covers_constraints() -> None:
    for key in ("ix", "uq", "ck", "fk", "pk"):
        assert key in NAMING_CONVENTION
    assert metadata.naming_convention == NAMING_CONVENTION
