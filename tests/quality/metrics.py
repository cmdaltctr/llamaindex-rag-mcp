"""Recall and reciprocal-rank metrics owned by the retrieval quality gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Copied and extended from:
# experiments/19-native-fts-vs-bm25-sparse-2026-08-29/summarise_eval.py


def _expected_sources(row: dict[str, Any]) -> list[str]:
    """Return one row's accepted source names."""
    if "expected_sources" in row:
        return [str(source) for source in row["expected_sources"]]
    return [str(row["expected_source"])]


def _src_match(source: str, expected: str) -> bool:
    """Match an absolute or relative source path to one expected file name."""
    name = Path(source or "").name
    return name == expected or expected in name


def _recall_mrr(rows: list[dict[str, Any]], k: int) -> tuple[float, float]:
    """Compute query hit-rate Recall@k and MRR@k.

    A row with multiple accepted sources is a hit when any accepted source
    appears in the first *k* results. This preserves Experiment 19's
    query-level metric while supporting source sets in the golden manifest.
    """
    hits = 0
    reciprocal = 0.0
    for row in rows:
        expected = _expected_sources(row)
        top_sources = row["sources"][:k]
        matching_ranks = [
            index
            for index, source in enumerate(top_sources, start=1)
            if any(_src_match(str(source), candidate) for candidate in expected)
        ]
        if matching_ranks:
            hits += 1
            reciprocal += 1.0 / matching_ranks[0]

    count = len(rows)
    return (hits / count if count else 0.0), (reciprocal / count if count else 0.0)
