"""The shared MetaData is empty in M0 and carries a naming convention."""

from newsdock_db.metadata import NAMING_CONVENTION, metadata


def test_metadata_has_no_tables_in_m0() -> None:
    assert len(metadata.tables) == 0


def test_naming_convention_covers_constraints() -> None:
    for key in ("ix", "uq", "ck", "fk", "pk"):
        assert key in NAMING_CONVENTION
    assert metadata.naming_convention == NAMING_CONVENTION
