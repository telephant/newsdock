"""Test helpers for rows with embeddings: known vectors, no model needed.

Lives in the package (not in a test folder) because apps may not import each
other's tests and pytest's importlib mode does not share sibling modules.
"""

from datetime import UTC, datetime

from newsdock_db.models import Article

DIMENSION = 768
NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)


def make_vec(*components: float) -> list[float]:
    """The given leading components, zero-padded to the column's 768 dimensions."""
    return [*components, *([0.0] * (DIMENSION - len(components)))]


def article(
    key: str,
    title: str,
    *,
    vec: list[float] | None = None,
    model: str | None = "m1",
    domain: str = "example.com",
    themes: list[str] | None = None,
    published_at: datetime = NOW,
) -> Article:
    """A canonical article row; `model` is stored only when a vector is given."""
    return Article(
        url_hash=key, gkg_record_id="x", slot="20261028120000",
        url=f"https://{domain}/{key}", title=title, domain=domain,
        published_at=published_at, themes=themes or [], persons=[], orgs=[],
        story_key=f"s {key}",
        embedding=vec, embedding_model=model if vec is not None else None,
    )  # fmt: skip
