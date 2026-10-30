"""Vector validation: nothing odd is ever stored or compared."""

import math
from collections.abc import Sequence

from newsdock_embedding.errors import BadEmbedding


def validate(vector: Sequence[float], dimension: int) -> None:
    """Raise BadEmbedding unless the vector has `dimension` finite numbers."""
    if len(vector) != dimension:
        raise BadEmbedding(f"expected {dimension} dimensions, got {len(vector)}")
    if not all(math.isfinite(value) for value in vector):
        raise BadEmbedding("vector contains a value that is not finite")
