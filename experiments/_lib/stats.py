"""Statistical output contract for experiment cells (Stage 4, task 4.4).

Enforces the ``design.md`` D16 reporting rules in code: per-query raw rows
with warm-up kept out of measured aggregates, paired bootstrap confidence
intervals for primary deltas, and interrupted cells recorded as status
strings rather than invented numeric failures.

Pure standard library; no numpy and no global random state.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

__all__ = [
    "REQUIRED_PER_QUERY_FIELDS",
    "VALID_CELL_STATUSES",
    "VALID_PHASES",
    "cell_record",
    "finalise_cells",
    "paired_bootstrap_ci",
    "split_warmup",
    "validate_per_query_rows",
]

REQUIRED_PER_QUERY_FIELDS: frozenset[str] = frozenset(
    {"cell_id", "query_id", "phase", "latency_ms", "metrics"}
)
VALID_PHASES: frozenset[str] = frozenset({"warmup", "measured"})
VALID_CELL_STATUSES: frozenset[str] = frozenset({"complete", "incomplete", "invalid"})

_STATUSES_REQUIRING_REASON = frozenset({"incomplete", "invalid"})


def _is_number(value: Any) -> bool:
    """Return True for real numbers, rejecting booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_per_query_rows(rows: Iterable[Mapping[str, Any]]) -> None:
    """Validate per-query raw output rows against the D16 contract.

    Every row must carry ``cell_id``, ``query_id``, ``phase``, ``latency_ms``
    and ``metrics``; ``phase`` must be ``"warmup"`` or ``"measured"``,
    ``latency_ms`` numeric, and ``metrics`` a mapping.

    Args:
        rows: Per-query raw metric rows.

    Raises:
        ValueError: Naming the offending row index and field.
    """
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"row {index} is not a mapping: {type(row).__name__}")

        missing = REQUIRED_PER_QUERY_FIELDS - set(row)
        if missing:
            raise ValueError(f"row {index} missing field(s): {sorted(missing)}")

        phase = row["phase"]
        if phase not in VALID_PHASES:
            raise ValueError(
                f"row {index} has unknown phase {phase!r} (valid: {sorted(VALID_PHASES)})"
            )

        latency = row["latency_ms"]
        if not _is_number(latency):
            raise ValueError(f"row {index} has non-numeric latency_ms {latency!r}")

        metrics = row["metrics"]
        if not isinstance(metrics, Mapping):
            raise ValueError(f"row {index} has non-mapping metrics {type(metrics).__name__}")


def split_warmup(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Split validated per-query rows into ``(warmup_rows, measured_rows)``.

    Warm-up repetitions never mix into measured aggregates (D16).  Rows are
    validated first so an unlabelled or invalid phase cannot silently drop
    out of both partitions.  Order within each partition is preserved.

    Args:
        rows: Per-query raw metric rows.

    Returns:
        A ``(warmup_rows, measured_rows)`` tuple.
    """
    materialised = list(rows)
    validate_per_query_rows(materialised)
    warmup = [row for row in materialised if row["phase"] == "warmup"]
    measured = [row for row in materialised if row["phase"] == "measured"]
    return warmup, measured


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """Return the ``fraction`` quantile with linear interpolation.

    Mirrors the default interpolation of :func:`statistics.quantiles` so the
    CI bounds are reproducible from the sorted resample means.
    """
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def paired_bootstrap_ci(
    paired_a: Sequence[float],
    paired_b: Sequence[float],
    *,
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int,
) -> dict[str, float]:
    """Paired bootstrap confidence interval for the mean difference (D16).

    Resampling draws indices jointly, so pairings between ``paired_a`` and
    ``paired_b`` survive every resample.  Deterministic for a given ``seed``
    through a private :class:`random.Random` instance; the module-level
    random state is never touched.

    Args:
        paired_a: Per-query metric values for arm A.
        paired_b: Per-query metric values for arm B, paired by index with A.
        n_resamples: Number of bootstrap resamples.
        confidence: Interval confidence level (for example ``0.95``).
        seed: Seed for the private random generator.

    Returns:
        ``{"n", "delta", "ci_low", "ci_high", "confidence"}`` where ``delta``
        is the observed mean difference and the CI bounds are percentile
        bootstrap limits of the resampled means.

    Raises:
        ValueError: When the sequences are empty or differ in length.
    """
    if len(paired_a) != len(paired_b):
        raise ValueError(
            f"paired bootstrap requires equal-length sequences: {len(paired_a)} vs {len(paired_b)}"
        )
    if not paired_a:
        raise ValueError("paired bootstrap requires at least one pair")

    n = len(paired_a)
    deltas = [float(a) - float(b) for a, b in zip(paired_a, paired_b, strict=True)]
    observed_delta = sum(deltas) / n

    # Bootstrap resampling of experiment deltas, not a crypto context.
    rng = random.Random(seed)  # noqa: S311
    resampled_means: list[float] = []
    for _ in range(n_resamples):
        total = 0.0
        for _ in range(n):
            total += deltas[rng.randrange(n)]
        resampled_means.append(total / n)
    resampled_means.sort()

    alpha = 1.0 - confidence
    return {
        "n": float(n),
        "delta": observed_delta,
        "ci_low": _percentile(resampled_means, alpha / 2.0),
        "ci_high": _percentile(resampled_means, 1.0 - alpha / 2.0),
        "confidence": confidence,
    }


def cell_record(
    *,
    status: str,
    reason: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Build one cell summary record (task 4.4.4).

    Interrupted or invalid cells are recorded as status strings with a
    reason; numeric quality values are never invented here.  Extra keyword
    fields (metrics, timings, artefact paths) pass through unchanged.

    Args:
        status: One of ``complete``, ``incomplete``, ``invalid``.
        reason: Mandatory non-empty explanation for ``incomplete``/``invalid``.
        **fields: Additional fields stored alongside status and reason.

    Returns:
        The assembled cell record dictionary.

    Raises:
        ValueError: On an unknown status or a missing mandatory reason.
    """
    if status not in VALID_CELL_STATUSES:
        raise ValueError(f"unknown cell status {status!r} (valid: {sorted(VALID_CELL_STATUSES)})")
    if status in _STATUSES_REQUIRING_REASON:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"cell status {status!r} requires a non-empty 'reason'")
    return {"status": status, "reason": reason, **fields}


def finalise_cells(cells: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalise a run's cell records without mutating the inputs.

    Any record lacking a ``status`` key becomes ``incomplete`` with reason
    ``"missing status"`` (an existing reason is preserved).  All statuses are
    validated, and ``incomplete``/``invalid`` records must carry a reason.

    Args:
        cells: Cell records as produced during a run.

    Returns:
        A new list of new record dictionaries; the input is never mutated.

    Raises:
        ValueError: On an unknown status or a missing mandatory reason.
    """
    finalised: list[dict[str, Any]] = []
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise ValueError(f"cell record is not a mapping: {type(cell).__name__}")
        record = dict(cell)
        if "status" not in record:
            record["status"] = "incomplete"
            if "reason" not in record:
                record["reason"] = "missing status"
        status = record["status"]
        if status not in VALID_CELL_STATUSES:
            raise ValueError(
                f"unknown cell status {status!r} (valid: {sorted(VALID_CELL_STATUSES)})"
            )
        if status in _STATUSES_REQUIRING_REASON:
            reason = record.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"cell status {status!r} requires a non-empty 'reason'")
        finalised.append(record)
    return finalised
