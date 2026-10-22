"""Embedding norm guard — the unit-norm contract at both vector boundaries.

Dense retrieval ranks by L2 distance over raw model vectors and converts
to cosine-like similarity at the store boundary.  That conversion is only
rank-equivalent to cosine when vectors are unit-normalised.  The 2026-08-23
investigation verified the property holds for the Ollama
``qwen3-embedding:0.6b`` path and every vector in the frozen Experiment 10b
index, but nothing enforced it — a model or provider swap would silently
degrade ranking with no error and no warning.  This module converts the
inherited property into an explicit contract (design D1): verify norms,
never rewrite them.

Boundary policy (design D2):

- **Ingest** (``core/ingestion/replacement.py``): fail closed.  A violating
  vector raises :class:`EmbeddingNormViolationError` before any node write,
  so the failure-safe replacement ordering keeps the previous searchable
  version intact.
- **Query** (``core/retrieval/dense.py``): warn and continue.  A violation
  logs once per process per model; results are still returned and a
  ``norm_guard`` diagnostic is attached when diagnostics are enabled.

The module is pure functions plus injected policy: ``enabled`` and
``tolerance`` arrive from the caller's ``EffectiveSettings`` (repo
invariant #9 — no settings singleton import), and nothing here imports
``config``, ``compose``, ``ingestion``, or ``retrieval`` (invariant #2).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: The setting named in guard errors so operators can act without
#: reading source.  The enable flag is named in the disable path only.
TOLERANCE_SETTING = "EMBEDDING__NORM_TOLERANCE"
ENABLE_SETTING = "EMBEDDING__NORM_GUARD_ENABLED"


class EmbeddingNormViolationError(RuntimeError):
    """A vector norm deviates from 1.0 beyond the configured tolerance."""

    def __init__(self, model_name: str, observed_norm: float, tolerance: float) -> None:
        self.model_name = model_name
        self.observed_norm = observed_norm
        self.tolerance = tolerance
        super().__init__(
            f"Embedding model '{model_name}' produced a vector with L2 norm "
            f"{observed_norm:.6f}, outside the unit-norm tolerance {tolerance} "
            f"(|norm - 1.0| <= {tolerance}). L2 ranking only behaves like "
            f"cosine for unit vectors. Use a normalising embedding model, or "
            f"adjust {TOLERANCE_SETTING} / set {ENABLE_SETTING}=false "
            f"explicitly if the provider is known to be off-norm."
        )


@dataclass(frozen=True)
class NormCheck:
    """One query-vector norm evaluation, for diagnostics."""

    observed_norm: float
    tolerance: float
    violation: bool

    def as_dict(self) -> dict:
        """Return the additive diagnostic attached per result row."""
        return {
            "enabled": True,
            "tolerance": self.tolerance,
            "observed_norm": self.observed_norm,
            "violation": self.violation,
        }


def l2_norm(vector: Sequence[float]) -> float:
    """Return the Euclidean (L2) norm of *vector*.

    An empty vector has norm 0.0 and therefore violates the unit-norm
    contract.  ``math.fsum`` keeps the sum-of-squares accurate for the
    dimensionality of production embedding vectors.
    """
    return math.sqrt(math.fsum(x * x for x in vector))


def is_within_tolerance(norm: float, tolerance: float) -> bool:
    """Return whether *norm* is within *tolerance* of 1.0 (inclusive)."""
    return abs(norm - 1.0) <= tolerance


def check_ingest_vectors(
    vectors: Sequence[Sequence[float]],
    *,
    model_name: str,
    enabled: bool = True,
    tolerance: float = 0.001,
) -> tuple[float, float] | None:
    """Verify storage-bound vectors; return the observed norm band.

    Args:
        vectors: Every vector about to be written for one source.
        model_name: Diagnostic embedding model name for error messages.
        enabled: Guard switch from the injected ``EffectiveSettings``.
        tolerance: Maximum permitted ``|norm - 1.0|`` (inclusive).

    Returns:
        ``(min_norm, max_norm)`` across all checked vectors, or ``None``
        when the guard is disabled (reporting what ran, not what did not).

    Raises:
        EmbeddingNormViolationError: When the worst vector deviates beyond
            *tolerance*.  The error names the model, the observed norm,
            the tolerance, and the controlling setting.
    """
    if not enabled:
        return None
    worst_norm: float | None = None
    worst_deviation = -1.0
    min_norm = math.inf
    max_norm = -math.inf
    saw_nan = False
    for vector in vectors:
        norm = l2_norm(vector)
        if math.isnan(norm):
            # NaN never wins a deviation comparison (every comparison
            # against it is False), so it is tracked separately and
            # always violates — a NaN vector must not slip through on
            # the strength of clean neighbours.
            saw_nan = True
            continue
        min_norm = min(min_norm, norm)
        max_norm = max(max_norm, norm)
        deviation = abs(norm - 1.0)
        if deviation > worst_deviation:
            worst_deviation = deviation
            worst_norm = norm
    if saw_nan:
        raise EmbeddingNormViolationError(model_name, math.nan, tolerance)
    if worst_norm is None:
        return None
    if not is_within_tolerance(worst_norm, tolerance):
        raise EmbeddingNormViolationError(model_name, worst_norm, tolerance)
    return (min_norm, max_norm)


def check_query_vector(
    vector: Sequence[float],
    *,
    model_name: str,
    enabled: bool = True,
    tolerance: float = 0.001,
) -> NormCheck | None:
    """Verify one query vector; warn once per process per model on violation.

    Args:
        vector: The query embedding about to feed dense search.
        model_name: Diagnostic embedding model name (warn-once key).
        enabled: Guard switch from the injected ``EffectiveSettings``.
        tolerance: Maximum permitted ``|norm - 1.0|`` (inclusive).

    Returns:
        The :class:`NormCheck` for diagnostics, or ``None`` when the guard
        is disabled.  Search results are returned either way — a degraded
        answer beats an outage (design D2).
    """
    if not enabled:
        return None
    norm = l2_norm(vector)
    violation = not is_within_tolerance(norm, tolerance)
    if violation and model_name not in _warned_norm_models:
        _warned_norm_models.add(model_name)
        logger.warning(
            "Query embedding norm violation: model '%s' produced L2 norm "
            "%.6f, outside tolerance %s (|norm - 1.0| <= %s). Dense L2 "
            "ranking is not cosine-equivalent for this vector; results are "
            "degraded but still returned. This warning is logged once per "
            "process per model. Adjust %s or set %s=false explicitly if "
            "the provider is known to be off-norm.",
            model_name,
            norm,
            tolerance,
            tolerance,
            TOLERANCE_SETTING,
            ENABLE_SETTING,
            extra={"model": model_name},
        )
    return NormCheck(observed_norm=norm, tolerance=tolerance, violation=violation)


# ── Process-local warn-once state ───────────────────────────────────────
# Matches the retrieval pipeline's `_warned_collections` pattern: a
# module-level set keyed by model, resettable so tests stay independent.
_warned_norm_models: set[str] = set()


def reset_warned_norm_models() -> None:
    """Clear the warn-once set (used by tests)."""
    _warned_norm_models.clear()
