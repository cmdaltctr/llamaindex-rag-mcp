"""Build the Experiment 3 fixture manifest, query set, and expected outcomes.

Everything here is analytic: the five synthetic rows carry hand-set
vectors and texts so the dense ordering, the BM25 ordering, the RRF
orderings (``rrf_k=60``) and the positive-threshold membership are all
derivable without touching production retrieval code.  The BM25 scores
are computed from the published BM25Okapi formula (k1=1.5, b=0.75,
RSJ idf with rank_bm25's epsilon clipping — no negative idf occurs in
this corpus) via an independent inline implementation.  The RRF values
are exact fractions.

Writes (refusing to clobber without ``--force``):

- ``fixtures/manifest.json`` — corpus, vectors, metadata, dense bands,
  BM25 expectations, RRF scenarios, fake reranker scores, constants.
- ``fixtures/queries.json`` — the single fixed query.
- ``fixtures/qrels.json`` — per-cell expected final outcomes.

Run (from the repository root)::

    uv run --no-sync python \\
        experiments/example/experiment-3-hybrid-filter-and-threshold-semantics/build_fixture.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = SCRIPT_DIR / "fixtures"

RRF_K = 60
TOP_K = 5
FETCH_K = 5
POSITIVE_THRESHOLD = 0.3
COLLECTION_NAME = "exp3_hybrid_filter_threshold_fixture"

# The query vector anchors dim 0; each row displaces exactly one other
# dimension so true L2 distances are clean and distinct.
QUERY_TEXT = "beacon harbour"
QUERY_VECTOR = [1.0, 0.0, 0.0, 0.0]

ROWS: list[dict[str, Any]] = [
    {
        "id": "row_E",
        "label": "E",
        "category": "allowed",
        # Strong dense + strong sparse (harbour x2, longest doc).
        "text": "harbour harbour opal cascade driftwood kestrel amber slate vellum juniper",
        "vector": [1.0, 0.5, 0.0, 0.0],
        "l2_distance": 0.5,
    },
    {
        "id": "row_A",
        "label": "A",
        "category": "allowed",
        # Strong dense, weak sparse (no query term -> BM25 score 0).
        "text": "silver orchard lantern velvet compass marble timber pasture",
        "vector": [1.0, 0.0, 1.0, 0.0],
        "l2_distance": 1.0,
    },
    {
        "id": "row_C",
        "label": "C",
        "category": "forbidden",
        # FORBIDDEN metadata, medium dense + second-strongest sparse.
        "text": "beacon beacon granite terrace quiver sombre ledger orchard",
        "vector": [1.0, 0.0, 0.0, 1.2],
        "l2_distance": 1.2,
    },
    {
        "id": "row_B",
        "label": "B",
        "category": "allowed",
        # Weak dense (below positive threshold) + strongest sparse.
        "text": "beacon beacon copper signal ferrite lantern",
        "vector": [1.0, 0.0, 3.0, 0.0],
        "l2_distance": 3.0,
    },
    {
        "id": "row_D",
        "label": "D",
        "category": "allowed",
        # Below positive dense threshold, keyword-only recovery candidate.
        "text": "harbour meadow cipher bramble falcon garnet thistle ridge",
        "vector": [1.0, 0.0, 0.0, 4.0],
        "l2_distance": 4.0,
    },
]

# Deterministic fake reranker scores (protocol §4 Factor D).  Chosen so
# the reranker-threshold semantics are observable: B (0.02) survives
# 0.3/30 = 0.01 while D (0.001) does not, and none would survive a raw
# 0.3 comparison — three distinguishable outcomes.
FAKE_RERANKER_SCORES: dict[str, float] = {
    "row_E": 0.95,
    "row_A": 0.5,
    "row_B": 0.02,
    "row_C": 0.44,
    "row_D": 0.001,
}

FILTERS: dict[str, dict[str, Any] | None] = {
    "none": None,
    "category_allowed": {"category": "allowed"},
    "category_eq_allowed": {"category": {"$eq": "allowed"}},
    "category_in_allowed": {"category": {"$in": ["allowed"]}},
}

STOP_WORDS = frozenset(
    """a an and are as at be but by for from has have he her his i in is it its
    of on or our she that the their them there these they this to was we were
    what when where which who will with you your""".split()
)


def _tokens(text: str) -> list[str]:
    """Word-boundary lowercase tokens minus stop words (mirrors the spec)."""
    import re

    return [t for t in re.findall(r"\b\w+\b", text.lower()) if t not in STOP_WORDS]


def _bm25_analytics() -> dict[str, Any]:
    """Score the corpus with the published BM25Okapi formula, independently.

    k1=1.5, b=0.75, RSJ idf ``ln((N - df + 0.5)/(df + 0.5))``.  No query
    term occurs in more than two of the five docs, so no idf is negative
    and rank_bm25's epsilon clipping is inert.
    """
    k1, b = 1.5, 0.75
    corpus = {row["id"]: _tokens(row["text"]) for row in ROWS}
    doc_ids = list(corpus)
    n_docs = len(doc_ids)
    avgdl = sum(len(corpus[doc]) for doc in doc_ids) / n_docs
    query_terms = _tokens(QUERY_TEXT)

    df: dict[str, int] = {}
    for term in query_terms:
        df[term] = sum(1 for doc in doc_ids if term in corpus[doc])
    idf = {
        term: math.log(n_docs - df[term] + 0.5) - math.log(df[term] + 0.5) for term in query_terms
    }

    scores: dict[str, float] = {}
    for doc in doc_ids:
        total = 0.0
        for term in query_terms:
            tf = corpus[doc].count(term)
            if tf == 0:
                continue
            norm = k1 * (1.0 - b + b * len(corpus[doc]) / avgdl)
            total += idf[term] * tf * (k1 + 1.0) / (tf + norm)
        scores[doc] = total

    ranked = sorted(
        ((doc, score) for doc, score in scores.items() if score > 0.0),
        key=lambda item: (-item[1], item[0]),
    )
    return {
        "k1": k1,
        "b": b,
        "avgdl": avgdl,
        "doc_lengths": {doc: len(corpus[doc]) for doc in doc_ids},
        "document_frequency": df,
        "idf": idf,
        "scores": scores,
        "expected_ordering": [doc for doc, _score in ranked],
        "zero_score_rows": sorted(doc for doc, score in scores.items() if score <= 0.0),
    }


def _rrf_scores(
    dense_order: list[str],
    sparse_order: list[str],
    k: int,
) -> dict[str, dict[str, Any]]:
    """Exact RRF table: 1/(k+rank_d) + 1/(k+rank_s) as fractions."""
    dense_rank = {doc: rank for rank, doc in enumerate(dense_order, start=1)}
    sparse_rank = {doc: rank for rank, doc in enumerate(sparse_order, start=1)}
    table: dict[str, dict[str, Any]] = {}
    for doc in dense_rank.keys() | sparse_rank.keys():
        parts = []
        if doc in dense_rank:
            parts.append(Fraction(1, k + dense_rank[doc]))
        if doc in sparse_rank:
            parts.append(Fraction(1, k + sparse_rank[doc]))
        total = sum(parts, Fraction(0))
        table[doc] = {
            "fused_score": float(total),
            "exact": f"{total.numerator}/{total.denominator}",
            "dense_rank": dense_rank.get(doc),
            "sparse_rank": sparse_rank.get(doc),
        }
    return table


def _dense_bands() -> dict[str, dict[str, Any]]:
    """Canonical-score endpoints for the two L2 reporting conventions.

    A store may convert ``1/(1+d)`` or ``1/(1+d^2)``; both are monotone
    in the true distance, so the analytic expectation is the closed band
    spanned by the two endpoints.  Row ordering and the 0.3 threshold
    membership hold under either convention by construction.
    """
    bands: dict[str, dict[str, Any]] = {}
    for row in ROWS:
        d = row["l2_distance"]
        endpoints = [1.0 / (1.0 + d * d), 1.0 / (1.0 + d)]
        bands[row["id"]] = {
            "l2_distance": d,
            "l2_distance_squared": d * d,
            "band_squared_convention": endpoints[0],
            "band_unsquared_convention": endpoints[1],
            "band_min": min(endpoints),
            "band_max": max(endpoints),
        }
    return bands


def _ordered(table: dict[str, dict[str, Any]]) -> list[str]:
    return [
        doc for doc, _ in sorted(table.items(), key=lambda item: (-item[1]["fused_score"], item[0]))
    ]


def build_expectations() -> dict[str, Any]:
    """Derive every analytic expectation from the fixture alone.

    Dense ordering follows the distinct L2 distances; the sparse ordering
    comes from the independent BM25 calculation; the RRF scenarios apply
    rank fusion to (a subset of) those orderings per the declared hybrid
    semantics.  Positive-threshold scenarios evaluate the dense threshold
    on dense evidence *before* fusion (spec §14 H4): only rows with
    qualifying dense scores may enter, so sparse-only rows drop out.
    """
    bm25 = _bm25_analytics()
    dense_order = [row["id"] for row in sorted(ROWS, key=lambda r: (r["l2_distance"], r["label"]))]
    sparse_order = bm25["expected_ordering"]
    qualifying = {"row_E", "row_A", "row_C"}  # bands lie above 0.3
    allowed = [row["id"] for row in ROWS if row["category"] == "allowed"]

    dense_allowed = [doc for doc in dense_order if doc in allowed]
    sparse_allowed = [doc for doc in sparse_order if doc in allowed]

    scenarios: dict[str, Any] = {
        "no_filter": {
            "dense_order": dense_order,
            "sparse_order": sparse_order,
            "rrf": _rrf_scores(dense_order, sparse_order, RRF_K),
        },
        "allowed_filter": {
            "dense_order": dense_allowed,
            "sparse_order": sparse_allowed,
            "rrf": _rrf_scores(dense_allowed, sparse_allowed, RRF_K),
        },
        "allowed_filter_positive_threshold": {
            # Dense evidence gated at 0.3 first (H4); only qualifying,
            # filter-eligible rows may contribute sparse rank too.
            "dense_order": [doc for doc in dense_allowed if doc in qualifying],
            "sparse_order": [doc for doc in sparse_allowed if doc in qualifying],
            "rrf": _rrf_scores(
                [doc for doc in dense_allowed if doc in qualifying],
                [doc for doc in sparse_allowed if doc in qualifying],
                RRF_K,
            ),
        },
    }
    for scenario in scenarios.values():
        scenario["expected_order"] = _ordered(scenario["rrf"])

    fused_allowed = scenarios["allowed_filter"]["expected_order"]
    gated = scenarios["allowed_filter_positive_threshold"]["expected_order"]
    rerank_threshold = POSITIVE_THRESHOLD / 30.0

    # Cell-by-cell expected outcomes (protocol §8 matrix + operator extras).
    cells: dict[str, dict[str, Any]] = {
        "cell_01_dense_allowed_thr0": {
            "scenario": "dense_allowed",
            "final_ids": dense_allowed,
            "score_kind": "dense_similarity_v1",
            "fused_scores": None,
        },
        "cell_02_hybrid_allowed_thr0": {
            "scenario": "allowed_filter",
            "final_ids": fused_allowed,
            "score_kind": "rrf_v1",
            "fused_scores": {
                doc: scenarios["allowed_filter"]["rrf"][doc]["fused_score"] for doc in fused_allowed
            },
        },
        "cell_03_hybrid_none_thr0": {
            "scenario": "no_filter",
            "final_ids": scenarios["no_filter"]["expected_order"],
            "score_kind": "rrf_v1",
            "fused_scores": {
                doc: scenarios["no_filter"]["rrf"][doc]["fused_score"]
                for doc in scenarios["no_filter"]["expected_order"]
            },
        },
        "cell_04_hybrid_allowed_thr_pos": {
            "scenario": "allowed_filter_positive_threshold",
            "final_ids": gated,
            "score_kind": "rrf_v1",
            "fused_scores": {
                doc: scenarios["allowed_filter_positive_threshold"]["rrf"][doc]["fused_score"]
                for doc in gated
            },
        },
        "cell_05_hybrid_allowed_thr_pos_fake_success": {
            "scenario": "allowed_filter_rerank_success",
            # Successful reranker re-scores the full filtered pool; the
            # threshold then uses reranker semantics: 0.3/30 = 0.01.
            "final_ids": [
                doc
                for doc in sorted(
                    fused_allowed,
                    key=lambda d: (-FAKE_RERANKER_SCORES[d], d),
                )
                if FAKE_RERANKER_SCORES[doc] >= rerank_threshold
            ],
            "score_kind": "reranker_sigmoid_v1",
            "reranker_scores": {doc: FAKE_RERANKER_SCORES[doc] for doc in fused_allowed},
            "effective_threshold": rerank_threshold,
        },
        "cell_06_hybrid_allowed_thr_pos_fake_failure": {
            # Failed reranker restores the pre-rerank dense-threshold rule
            # (spec §14 H5): identical outcome to cell 4.
            "scenario": "allowed_filter_positive_threshold",
            "final_ids": gated,
            "score_kind": "rrf_v1",
            "fused_scores": {
                doc: scenarios["allowed_filter_positive_threshold"]["rrf"][doc]["fused_score"]
                for doc in gated
            },
        },
        "cell_07_dense_eq_allowed_thr0": {
            "scenario": "dense_allowed",
            "final_ids": dense_allowed,
            "score_kind": "dense_similarity_v1",
            "fused_scores": None,
        },
        "cell_08_hybrid_eq_allowed_thr0": {
            "scenario": "allowed_filter",
            "final_ids": fused_allowed,
            "score_kind": "rrf_v1",
            "fused_scores": {
                doc: scenarios["allowed_filter"]["rrf"][doc]["fused_score"] for doc in fused_allowed
            },
        },
        "cell_09_dense_in_allowed_thr0": {
            "scenario": "dense_allowed",
            "final_ids": dense_allowed,
            "score_kind": "dense_similarity_v1",
            "fused_scores": None,
        },
        "cell_10_hybrid_in_allowed_thr0": {
            "scenario": "allowed_filter",
            "final_ids": fused_allowed,
            "score_kind": "rrf_v1",
            "fused_scores": {
                doc: scenarios["allowed_filter"]["rrf"][doc]["fused_score"] for doc in fused_allowed
            },
        },
    }

    return {
        "bm25": bm25,
        "dense_order": dense_order,
        "dense_bands": _dense_bands(),
        "dense_threshold_membership": {
            "threshold": POSITIVE_THRESHOLD,
            "qualifying": sorted(qualifying),
            "non_qualifying": sorted(set(r["id"] for r in ROWS) - qualifying),
        },
        "scenarios": scenarios,
        "allowed_rows": sorted(allowed),
        "forbidden_rows": sorted(r["id"] for r in ROWS if r["category"] == "forbidden"),
        "cells": cells,
    }


def _write_json(path: Path, payload: Any, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"refusing to overwrite {path} without --force")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"wrote {path.relative_to(SCRIPT_DIR)} sha256:{digest}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Experiment 3 fixtures")
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    args = parser.parse_args()

    expectations = build_expectations()
    manifest = {
        "template_id": "example/experiment-3-hybrid-filter-and-threshold-semantics",
        "collection_name": COLLECTION_NAME,
        "constants": {
            "rrf_k": RRF_K,
            "top_k": TOP_K,
            "fetch_k": FETCH_K,
            "positive_threshold": POSITIVE_THRESHOLD,
            "rerank_threshold_scale": 30.0,
        },
        "query": {"id": "q1", "text": QUERY_TEXT, "vector": QUERY_VECTOR},
        "rows": [
            {
                "id": row["id"],
                "label": row["label"],
                "category": row["category"],
                "text": row["text"],
                "vector": row["vector"],
                "metadata": {
                    "category": row["category"],
                    "row_label": row["label"],
                    "file_path": f"fixture://exp3/{row['label']}",
                },
            }
            for row in ROWS
        ],
        "filters": {name: (flt or None) for name, flt in FILTERS.items()},
        "fake_reranker_scores": FAKE_RERANKER_SCORES,
        "expectations": expectations,
    }
    _write_json(FIXTURES_DIR / "manifest.json", manifest, args.force)
    _write_json(
        FIXTURES_DIR / "queries.json",
        {"queries": [{"id": "q1", "text": QUERY_TEXT}]},
        args.force,
    )
    _write_json(
        FIXTURES_DIR / "qrels.json",
        {
            "query_id": "q1",
            "allowed_rows": expectations["allowed_rows"],
            "forbidden_rows": expectations["forbidden_rows"],
            "cells": expectations["cells"],
        },
        args.force,
    )


if __name__ == "__main__":
    main()
