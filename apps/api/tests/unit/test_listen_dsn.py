"""listen_dsn: a SQLAlchemy URL becomes a psycopg conninfo (no database needed)."""

from newsdock_api.adapters.listener import listen_dsn
from psycopg.conninfo import conninfo_to_dict


def test_listen_dsn_turns_a_sqlalchemy_url_into_a_psycopg_conninfo() -> None:
    dsn = listen_dsn("postgresql+psycopg://u:p%40ss@h:5433/db")
    parts = conninfo_to_dict(dsn)
    assert (parts["user"], parts["password"], parts["host"]) == ("u", "p@ss", "h")
    assert (parts["port"], parts["dbname"]) == ("5433", "db")
