"""Store-neutral evaluation of the metadata-filter contract.

Dense stores apply the ChromaDB-shaped ``where`` clause through their native
query APIs.  The in-memory BM25 fallback uses this evaluator so hybrid
retrieval constrains both branches with the same logical query predicate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_COMPARISON_OPS = frozenset({"$eq", "$ne", "$gt", "$gte", "$lt", "$lte"})
_SET_OPS = frozenset({"$in", "$nin"})
_BOOLEAN_OPS = frozenset({"$and", "$or"})
_ALL_OPS = _COMPARISON_OPS | _SET_OPS | _BOOLEAN_OPS
_MISSING = object()


def matches_metadata_filter(metadata: Mapping[str, Any], where: dict | None) -> bool:
    """Return whether *metadata* satisfies a ChromaDB-shaped filter.

    Missing-key semantics match the cross-store contract: missing values
    satisfy ``$ne`` and ``$nin`` and fail equality, membership, and ordered
    comparisons.  Malformed or unsupported filters raise ``ValueError``
    instead of silently broadening sparse eligibility.

    Args:
        metadata: One chunk's user metadata.
        where: ChromaDB-style filter, or ``None``/empty for no constraint.

    Returns:
        ``True`` when the row is eligible.

    Raises:
        ValueError: If the filter shape or operator is unsupported.
    """
    if not where:
        return True
    if not isinstance(where, dict):
        raise ValueError("metadata_filter must be a dict")

    outcomes: list[bool] = []
    for key, condition in where.items():
        if key in _BOOLEAN_OPS:
            clauses = _require_clause_list(key, condition)
            evaluated = [matches_metadata_filter(metadata, clause) for clause in clauses]
            outcomes.append(all(evaluated) if key == "$and" else any(evaluated))
            continue
        if key.startswith("$"):
            raise ValueError(f"Unsupported filter operator {key!r}. Supported: {sorted(_ALL_OPS)}")
        outcomes.append(_matches_field(metadata.get(key, _MISSING), key, condition))
    return all(outcomes)


def _matches_field(actual: object, field: str, condition: object) -> bool:
    if not isinstance(condition, dict):
        return actual is not _MISSING and actual == condition
    if not condition:
        raise ValueError(f"Filter for field {field!r} is an empty operator dict.")

    outcomes: list[bool] = []
    for operator, expected in condition.items():
        if operator not in _ALL_OPS:
            raise ValueError(
                f"Unsupported filter operator {operator!r}. Supported: {sorted(_ALL_OPS)}"
            )
        if operator in _BOOLEAN_OPS:
            raise ValueError(
                f"Boolean operator {operator!r} is only valid at the top level of a where clause."
            )
        outcomes.append(_matches_leaf(actual, operator, expected))
    return all(outcomes)


def _matches_leaf(actual: object, operator: str, expected: object) -> bool:
    if operator == "$eq":
        return actual is not _MISSING and actual == expected
    if operator == "$ne":
        return actual is _MISSING or actual != expected
    if operator in _SET_OPS:
        if not isinstance(expected, Sequence) or isinstance(expected, (str, bytes, bytearray)):
            raise ValueError(
                f"{operator} requires a list of values, got {type(expected).__name__}."
            )
        contained = actual is not _MISSING and actual in expected
        return contained if operator == "$in" else not contained
    if actual is _MISSING:
        return False
    try:
        if operator == "$gt":
            return actual > expected
        if operator == "$gte":
            return actual >= expected
        if operator == "$lt":
            return actual < expected
        if operator == "$lte":
            return actual <= expected
    except TypeError:
        return False
    raise ValueError(f"Unsupported filter operator {operator!r}")


def _require_clause_list(operator: str, value: object) -> list[dict]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{operator} requires a non-empty list of where clauses.")
    if any(not isinstance(clause, dict) or not clause for clause in value):
        raise ValueError(f"Every {operator} sub-clause must be a non-empty where dict.")
    return value
