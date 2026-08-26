#!/usr/bin/env python3
"""Generate the committed analytic fixtures for Experiment 2.

Writes (deterministically, pure standard library):

- ``fixtures/manifest.json`` — the corpus: one section per fixture with
  document ids, texts, metadata, and the exact precomputed embedding
  vectors (the experiment never runs an embedding model).
- ``fixtures/queries.json`` — one analytic query vector and query text
  per fixture.
- ``fixtures/qrels.json`` — the pre-registered expected outcomes:
  expected strict orderings with labelled tie-equivalence groups,
  expected threshold membership per pinned canonical threshold, and
  expected metadata-filter membership.

Expected outcomes are derived analytically from the committed vectors
(exact float64 L2 distance, canonical score ``1 / (1 + d)``) BEFORE any
store run.  The generator self-validates that every pinned threshold
keeps a safety margin from every attainable score so float32 storage
quantisation in either store cannot flip membership.

Run from the repository root:

    uv run --no-sync python \\
        experiments/example/experiment-2-dense-cross-store-score-parity/make_fixtures.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = SCRIPT_DIR / "fixtures"

# Pinned canonical thresholds applied to every fixture (protocol §9).
PINNED_THRESHOLDS: list[float] = [0.9, 0.7, 0.55, 0.45, 0.35, 0.3]
# Minimum safety margin between any threshold and any attainable score.
_THRESHOLD_MARGIN = 0.005
# Distances closer than this are treated as ties (analytic construction
# makes true ties bit-exact; the epsilon only groups them).
_TIE_EPSILON = 1e-9

QUERY = [1.0, 0.0, 0.0, 0.0]


def _rotation_fixture() -> dict[str, Any]:
    """Progressively rotated unit vectors in the x-y plane."""
    docs: dict[str, Any] = {"exact": [1.0, 0.0, 0.0, 0.0]}
    for degrees in (15, 30, 45, 60, 90):
        radians = math.radians(degrees)
        docs[f"rot{degrees}"] = [math.cos(radians), math.sin(radians), 0.0, 0.0]
    return docs


# Fixture corpus: fixture id -> {doc id -> vector}.  All vectors are
# analytically known relative to QUERY.
FIXTURE_VECTORS: dict[str, dict[str, list[float]]] = {
    "f1_exact_ortho_opposite": {
        "f1_exact": [1.0, 0.0, 0.0, 0.0],
        "f1_ortho": [0.0, 1.0, 0.0, 0.0],
        "f1_opposite": [-1.0, 0.0, 0.0, 0.0],
        "f1_far": [-2.0, 0.0, 0.0, 0.0],
    },
    "f2_progressive_rotation": _rotation_fixture(),
    "f3_duplicate_ties": {
        "f3_exact": [1.0, 0.0, 0.0, 0.0],
        "f3_t1a": [0.0, 1.0, 0.0, 0.0],
        "f3_t1b": [0.0, -1.0, 0.0, 0.0],
        "f3_t2a": [0.0, 2.0, 0.0, 0.0],
        "f3_t2b": [0.0, 0.0, 2.0, 0.0],
    },
    "f4_unnormalised_scale": {
        "f4_one": [1.0, 0.0, 0.0, 0.0],
        "f4_half": [0.5, 0.0, 0.0, 0.0],
        "f4_two": [2.0, 0.0, 0.0, 0.0],
        "f4_three": [3.0, 0.0, 0.0, 0.0],
    },
    "f5_metadata_filters": {
        "f5_a": [1.0, 0.0, 0.0, 0.0],
        "f5_b": [0.0, 1.0, 0.0, 0.0],
        "f5_c": [0.0, 0.0, 1.0, 0.0],
        "f5_d": [0.0, 0.0, 0.0, 1.0],
        "f5_e": [0.0, 2.0, 0.0, 0.0],
    },
}

# Metadata: filter-bearing metadata lives on the f5 fixture; every other
# fixture carries only provenance metadata.
FIXTURE_METADATA: dict[str, dict[str, dict[str, Any]]] = {
    fixture_id: {doc_id: {"fixture": fixture_id, "doc": doc_id} for doc_id in docs}
    for fixture_id, docs in FIXTURE_VECTORS.items()
}
_F5 = "f5_metadata_filters"
FIXTURE_METADATA[_F5] = {
    "f5_a": {"fixture": _F5, "doc": "f5_a", "category": "alpha", "year": 2022, "tag": "x"},
    "f5_b": {"fixture": _F5, "doc": "f5_b", "category": "beta", "year": 2023, "tag": "y"},
    "f5_c": {"fixture": _F5, "doc": "f5_c", "category": "gamma", "year": 2024, "tag": "x"},
    "f5_d": {"fixture": _F5, "doc": "f5_d", "category": "beta", "year": 2022, "tag": "y"},
    "f5_e": {"fixture": _F5, "doc": "f5_e", "category": "alpha", "year": 2024, "tag": "z"},
}

# Chroma-shaped metadata filters (the store-neutral filter language,
# ADR-034).  Includes an $in operator filter and a nested boolean
# filter with a comparison operator (protocol H4).
FILTERS: dict[str, dict[str, Any]] = {
    "eq_beta": {"category": {"$eq": "beta"}},
    "in_alpha_gamma": {"category": {"$in": ["alpha", "gamma"]}},
    "and_beta_year_gte_2023": {"$and": [{"category": {"$eq": "beta"}}, {"year": {"$gte": 2023}}]},
    "or_tag_z_or_year_lt_2023": {"$or": [{"tag": {"$eq": "z"}}, {"year": {"$lt": 2023}}]},
    "nin_tag_y": {"tag": {"$nin": ["y"]}},
}


def _l2(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


def _canonical(distance: float) -> float:
    return 1.0 / (1.0 + distance)


def _matches(doc_meta: dict[str, Any], leaf: dict[str, Any]) -> bool:
    field, clause = next(iter(leaf.items()))
    value = doc_meta.get(field)
    if isinstance(clause, dict):
        for op, operand in clause.items():
            if op == "$eq" and not (value is not None and value == operand):
                return False
            if op == "$ne" and not (value is None or value != operand):
                return False
            if op == "$in" and not (isinstance(value, list) or value in operand):
                return False
            if op == "$nin" and not (value is None or value not in operand):
                return False
            if op == "$gt" and not (value is not None and value > operand):
                return False
            if op == "$gte" and not (value is not None and value >= operand):
                return False
            if op == "$lt" and not (value is not None and value < operand):
                return False
            if op == "$lte" and not (value is not None and value <= operand):
                return False
        return True
    return value is not None and value == clause


def _filter_membership(meta_by_id: dict[str, dict[str, Any]], where: dict[str, Any]) -> list[str]:
    """Evaluate a Chroma-shaped where clause in pure Python (ground truth)."""
    matched = []
    for doc_id, meta in meta_by_id.items():
        clauses: list[dict[str, Any]] = []
        for key, value in where.items():
            if key == "$and":
                if all(_matches(meta, c) for c in value):
                    clauses.append({})
            elif key == "$or":
                if any(_matches(meta, c) for c in value):
                    clauses.append({})
            elif _matches(meta, {key: value}):
                clauses.append({})
        if len(clauses) == len(where):
            matched.append(doc_id)
    return sorted(matched)


def build_expectations() -> dict[str, Any]:
    """Derive the pre-registered expected outcomes from the committed vectors."""
    qrels: dict[str, Any] = {"thresholds": PINNED_THRESHOLDS, "filters": FILTERS, "fixtures": {}}
    for fixture_id, vectors in FIXTURE_VECTORS.items():
        distances = {doc_id: _l2(QUERY, vec) for doc_id, vec in vectors.items()}

        # Group docs into tie sets by distance, preserving farthest-first order.
        ordered = sorted(distances, key=lambda doc: (distances[doc], doc))
        tie_groups: list[list[str]] = []
        for doc_id in ordered:
            if tie_groups and abs(distances[doc_id] - distances[tie_groups[-1][0]]) < _TIE_EPSILON:
                tie_groups[-1].append(doc_id)
            else:
                tie_groups.append([doc_id])

        scores = {doc_id: _canonical(d) for doc_id, d in distances.items()}
        membership = {
            f"{threshold:.2f}": sorted(doc for doc, s in scores.items() if s >= threshold)
            for threshold in PINNED_THRESHOLDS
        }
        # Margin self-check: no attainable score may sit on a threshold.
        for doc, score in scores.items():
            for threshold in PINNED_THRESHOLDS:
                if abs(score - threshold) < _THRESHOLD_MARGIN:
                    raise SystemExit(
                        f"fixture {fixture_id} doc {doc} score {score!r} sits within "
                        f"{_THRESHOLD_MARGIN} of pinned threshold {threshold}; "
                        "adjust the threshold list or the fixture geometry"
                    )

        expected_filters = {}
        if fixture_id == "f5_metadata_filters":
            expected_filters = {
                name: _filter_membership(FIXTURE_METADATA[fixture_id], where)
                for name, where in FILTERS.items()
            }

        qrels["fixtures"][fixture_id] = {
            "query_vector": QUERY,
            "expected_distances": {doc: round(d, 12) for doc, d in distances.items()},
            "expected_order_near_to_far": ordered,
            "tie_groups": tie_groups,
            "expected_threshold_membership": membership,
            "expected_filter_membership": expected_filters,
        }
    return qrels


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    corpus = {
        "dimension": len(QUERY),
        "canonical_score_formula": "1 / (1 + L2)",
        "fixtures": {
            fixture_id: {
                "documents": [
                    {
                        "id": doc_id,
                        "text": f"{doc_id} analytic fixture document.",
                        "metadata": FIXTURE_METADATA[fixture_id][doc_id],
                        "embedding": vector,
                    }
                    for doc_id, vector in sorted(vectors.items())
                ],
            }
            for fixture_id, vectors in FIXTURE_VECTORS.items()
        },
    }
    queries = {
        fixture_id: {
            "query_id": f"{fixture_id}::q",
            "text": f"exp2 analytic query {fixture_id}",
            "vector": QUERY,
        }
        for fixture_id in FIXTURE_VECTORS
    }
    qrels = build_expectations()

    _write_json(FIXTURES_DIR / "manifest.json", corpus)
    _write_json(FIXTURES_DIR / "queries.json", queries)
    _write_json(FIXTURES_DIR / "qrels.json", qrels)
    total = sum(len(f["documents"]) for f in corpus["fixtures"].values())
    print(
        f"wrote {total} fixture documents across "
        f"{len(corpus['fixtures'])} fixtures to {FIXTURES_DIR}"
    )


if __name__ == "__main__":
    main()
