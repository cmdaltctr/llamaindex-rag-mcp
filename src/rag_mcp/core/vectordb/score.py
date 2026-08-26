"""Store-neutral dense-score semantics shared by vector-store adapters.

The public retrieval layer consumes one canonical score kind.  Adapters
convert their native L2 distance at the boundary so core retrieval never
needs to know which backend produced a row or what its native field was
called.
"""

from __future__ import annotations

import math

DENSE_SCORE_KIND = "dense_similarity_v1"
"""Higher-is-better bounded similarity derived monotonically from L2 distance."""


def require_l2_metric(metric: object, *, backend: str, setting: str) -> None:
    """Fail clearly when an adapter is configured for a non-L2 metric."""
    resolved = str(metric or "l2").lower()
    if resolved != "l2":
        raise ValueError(
            f"{backend} uses unsupported dense metric {resolved!r}; "
            f"dense_similarity_v1 requires {setting}='l2'."
        )


def canonical_score_from_l2(distance: float | None, *, backend: str) -> float:
    """Convert a native L2 distance to ``dense_similarity_v1``.

    The canonical contract intentionally claims only a bounded, monotonic
    transform: ``1 / (1 + distance)``.  It does not claim cosine similarity
    or exact numeric equality between stores whose native L2 implementations
    may report different distance scaling.

    Args:
        distance: Native non-negative L2 distance.
        backend: Backend name included in actionable contract errors.

    Returns:
        A finite score in ``(0, 1]`` where larger means closer.

    Raises:
        ValueError: If the backend omits the distance or returns an invalid
            value that cannot satisfy the canonical contract.
    """
    if distance is None:
        raise ValueError(f"{backend} dense query returned no L2 distance")
    value = float(distance)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{backend} dense query returned invalid L2 distance {distance!r}")
    return 1.0 / (1.0 + value)
