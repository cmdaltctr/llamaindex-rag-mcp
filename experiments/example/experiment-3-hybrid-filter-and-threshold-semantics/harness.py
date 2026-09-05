"""Experiment 3 harness: fixture doubles, cell matrix, branch traces.

Support module for ``run_eval.py``.  Holds the deterministic test
doubles (protocol §4 Factor D), the 10-cell matrix, the branch-level
candidate traces (protocol §15) built from the same production
functions the pipeline calls, the trace-only final composition used as
a cross-check, and the hypothesis input collector for the §14 gates.
"""

from __future__ import annotations

from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from pydantic import PrivateAttr

FILTERED_HYBRID_CELLS = (
    "cell_02_hybrid_allowed_thr0",
    "cell_04_hybrid_allowed_thr_pos",
    "cell_05_hybrid_allowed_thr_pos_fake_success",
    "cell_06_hybrid_allowed_thr_pos_fake_failure",
    "cell_08_hybrid_eq_allowed_thr0",
    "cell_10_hybrid_in_allowed_thr0",
)


# ── Fixture doubles (protocol §4 Factor D: test seams, not models) ─────


class FixtureEmbedModel(BaseEmbedding):
    """Returns the fixed precomputed query vector; never touches network.

    A real ``BaseEmbedding`` subclass because the LlamaIndex settings
    setter validates the type; only the query path is ever exercised by
    the dense branch (``_embed_query`` reads ``model_name`` then calls
    ``get_query_embedding``).
    """

    model_name: str = "fixture-fake-embed-model-v1"
    _vector: list[float] = PrivateAttr(default_factory=list)

    def __init__(self, vector: list[float], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._vector = [float(component) for component in vector]

    def _get_query_embedding(self, query: str) -> list[float]:
        return list(self._vector)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return list(self._vector)

    def _get_text_embedding(self, text: str) -> list[float]:
        return list(self._vector)


class FakeSuccessReranker:
    """Deterministic reranker double: assigns the fixture's known scores.

    Mirrors the production contract in ``core/retrieval/reranker.py``:
    sets ``score`` and ``_reranked=True`` per row, sorts descending and
    truncates to ``top_k``; clears ``last_failure_reason`` per call.
    """

    backend_name = "FakeSuccessReranker"
    _model_id = "fake-double://success/v1"

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = dict(scores)
        self.last_failure_reason: str | None = None

    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        self.last_failure_reason = None
        if not results:
            return results
        for row in results:
            row_id = str(row["id"])
            if row_id not in self.scores:
                raise ValueError(f"fixture double has no score for row {row_id!r}")
            row["score"] = float(self.scores[row_id])
            row["_reranked"] = True
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]


class FakeFailureReranker:
    """Deterministic failing double: returns inputs, records the reason.

    Mirrors the production failure path: rows keep their pre-rerank
    scores with ``_reranked=False`` and ``last_failure_reason`` explains
    the failure so the pipeline can restore pre-rerank semantics.
    """

    backend_name = "FakeFailureReranker"
    _model_id = "fake-double://failure/v1"

    def __init__(self, reason: str) -> None:
        self._reason = reason
        self.last_failure_reason: str | None = None

    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        self.last_failure_reason = self._reason
        for row in results:
            row["_reranked"] = False
        return results[:top_k]


def build_cell_matrix() -> list[dict[str, Any]]:
    """Return the 10-cell matrix (6 protocol cells + 4 operator extras)."""
    return [
        {
            "id": "cell_01_dense_allowed_thr0",
            "factors": {
                "mode": "dense",
                "filter": "category_allowed",
                "threshold": 0.0,
                "rerank": "off",
            },
        },
        {
            "id": "cell_02_hybrid_allowed_thr0",
            "factors": {
                "mode": "hybrid_bm25",
                "filter": "category_allowed",
                "threshold": 0.0,
                "rerank": "off",
            },
        },
        {
            "id": "cell_03_hybrid_none_thr0",
            "factors": {"mode": "hybrid_bm25", "filter": "none", "threshold": 0.0, "rerank": "off"},
        },
        {
            "id": "cell_04_hybrid_allowed_thr_pos",
            "factors": {
                "mode": "hybrid_bm25",
                "filter": "category_allowed",
                "threshold": 0.3,
                "rerank": "off",
            },
        },
        {
            "id": "cell_05_hybrid_allowed_thr_pos_fake_success",
            "factors": {
                "mode": "hybrid_bm25",
                "filter": "category_allowed",
                "threshold": 0.3,
                "rerank": "fake_success",
            },
        },
        {
            "id": "cell_06_hybrid_allowed_thr_pos_fake_failure",
            "factors": {
                "mode": "hybrid_bm25",
                "filter": "category_allowed",
                "threshold": 0.3,
                "rerank": "fake_failure",
            },
        },
        {
            "id": "cell_07_dense_eq_allowed_thr0",
            "factors": {
                "mode": "dense",
                "filter": "category_eq_allowed",
                "threshold": 0.0,
                "rerank": "off",
            },
        },
        {
            "id": "cell_08_hybrid_eq_allowed_thr0",
            "factors": {
                "mode": "hybrid_bm25",
                "filter": "category_eq_allowed",
                "threshold": 0.0,
                "rerank": "off",
            },
        },
        {
            "id": "cell_09_dense_in_allowed_thr0",
            "factors": {
                "mode": "dense",
                "filter": "category_in_allowed",
                "threshold": 0.0,
                "rerank": "off",
            },
        },
        {
            "id": "cell_10_hybrid_in_allowed_thr0",
            "factors": {
                "mode": "hybrid_bm25",
                "filter": "category_in_allowed",
                "threshold": 0.0,
                "rerank": "off",
            },
        },
    ]


# ── Branch-level traces (protocol §15) ────────────────────────────────


def branch_traces(
    fixture: dict[str, Any],
    *,
    mode: str,
    rerank: str,
    threshold: float,
    metadata_filter: dict[str, Any] | None,
    store: Any,
    collection_name: str,
    query_text: str,
    fetch_k: int,
) -> dict[str, Any]:
    """Capture branch candidates with the same production functions.

    Dense rows come from ``_dense_query_rows``; sparse candidates from
    ``BM25SparseRetriever.query`` (the class the pipeline instantiates);
    fusion from ``rrf_with_metadata`` with the pipeline's gating rule
    (positive dense threshold evaluates on dense evidence *before*
    fusion when no reranker is active; the failed-reranker restore path
    re-runs the same gated fusion).
    """
    from omrg.core.retrieval.dense import _dense_query_rows
    from omrg.core.retrieval.filters import matches_metadata_filter
    from omrg.core.retrieval.fusion import rrf_with_metadata
    from omrg.core.retrieval.sparse import BM25SparseRetriever

    dense_rows = _dense_query_rows(store, collection_name, query_text, fetch_k, metadata_filter)
    dense_trace = [
        {"id": row["id"], "score": float(row["score"]), "score_kind": row["score_kind"]}
        for row in dense_rows
    ]

    sparse_rows: list[tuple[int, str, str, dict]] = []
    if mode == "hybrid_bm25":
        sparse_rows = BM25SparseRetriever(collection_name, store=store).query(
            query_text, fetch_k, metadata_filter=metadata_filter
        )
    sparse_trace = [
        {"rank": rank, "id": doc_id, "category": metadata.get("category")}
        for rank, doc_id, _text, metadata in sparse_rows
    ]

    trace: dict[str, Any] = {
        "dense": dense_trace,
        "sparse": sparse_trace,
        "dense_branch_filter_violations": sum(
            1 for row in dense_rows if not matches_metadata_filter(row["metadata"], metadata_filter)
        ),
        "sparse_branch_filter_violations": sum(
            1
            for _rank, _doc_id, _text, metadata in sparse_rows
            if not matches_metadata_filter(metadata, metadata_filter)
        ),
    }
    if mode != "hybrid_bm25":
        return trace

    def _fuse(dense_stage: list[dict], sparse_ids: list[str]) -> list[dict[str, Any]]:
        eligible = set(sparse_ids)
        sparse_stage = [
            {"id": item["id"], "text": "", "metadata": {"category": item["category"]}}
            for item in sparse_trace
            if item["id"] in eligible
        ]
        fused = rrf_with_metadata(dense_stage, sparse_stage, k=fixture["constants"]["rrf_k"])
        return fused[:fetch_k]

    sparse_ids = [item["id"] for item in sparse_trace]
    if rerank in ("off", "fake_failure") and threshold > 0.0:
        # Gated stage: dense evidence qualifies before fusion; sparse
        # candidates without qualifying dense evidence are ineligible.
        gated_dense = [row for row in dense_rows if float(row["score"]) >= threshold]
        qualifying_ids = {str(row["id"]) for row in gated_dense}
        gated_sparse = [doc_id for doc_id in sparse_ids if doc_id in qualifying_ids]
        trace["eligibility"] = {
            "dense_qualifying_ids": sorted(qualifying_ids),
            "sparse_eligible_ids": gated_sparse,
        }
        trace["fused"] = _fuse(gated_dense, gated_sparse)
        if rerank == "fake_failure":
            # Pre-rerank (ungated) pool the pipeline fuses before the
            # failed reranker triggers the gated re-run.
            trace["fused_pre_rerank"] = _fuse(dense_rows, sparse_ids)
    else:
        trace["fused"] = _fuse(dense_rows, sparse_ids)
    return trace


def compose_final(
    fixture: dict[str, Any],
    *,
    trace: dict[str, Any],
    mode: str,
    rerank: str,
    threshold: float,
    top_k: int,
) -> list[dict[str, Any]]:
    """Compose the expected final rows from the branch trace alone."""
    if mode == "dense":
        kept = [
            dict(row) for row in trace["dense"] if threshold <= 0.0 or row["score"] >= threshold
        ]
        return kept[:top_k]
    if rerank == "fake_success":
        scores = fixture["fake_reranker_scores"]
        reranked = sorted(
            ({"id": row["id"], "score": float(scores[str(row["id"])])} for row in trace["fused"]),
            key=lambda row: (-row["score"], row["id"]),
        )
        effective_threshold = threshold / 30.0
        return [row for row in reranked if row["score"] >= effective_threshold][:top_k]
    return [{"id": row["id"], "score": float(row["fused_score"])} for row in trace["fused"]][:top_k]


def hypothesis_inputs(
    records: list[dict[str, Any]],
    qrels: dict[str, Any],
    *,
    static_check_rel: str,
) -> dict[str, Any]:
    """Collect the raw numbers the protocol §14 gates evaluate on."""
    by_id = {rec["cell_id"]: rec for rec in records if rec["status"] == "complete"}
    metrics = {cid: rec["per_query"][0]["metrics"] for cid, rec in by_id.items()}

    filtered_hybrid = {cid: metrics[cid] for cid in FILTERED_HYBRID_CELLS if cid in metrics}
    cell_03 = metrics.get("cell_03_hybrid_none_thr0", {})
    cell_04 = metrics.get("cell_04_hybrid_allowed_thr_pos", {})
    cell_05 = metrics.get("cell_05_hybrid_allowed_thr_pos_fake_success", {})
    cell_06 = metrics.get("cell_06_hybrid_allowed_thr_pos_fake_failure", {})
    forbidden = set(qrels["forbidden_rows"])

    sparse_traces = {
        cid: by_id[cid]["traces"]["sparse"] for cid in FILTERED_HYBRID_CELLS if cid in by_id
    }
    return {
        "h1_forbidden_leaks_by_cell": {
            cid: m["forbidden_leak_count"] for cid, m in filtered_hybrid.items()
        },
        "h2_sparse_branch_violations_by_cell": {
            cid: m["sparse_branch_filter_violations"] for cid, m in filtered_hybrid.items()
        },
        "h2_forbidden_absent_from_filtered_sparse_traces": {
            cid: all(item["id"] not in forbidden for item in trace)
            for cid, trace in sparse_traces.items()
        },
        "h3": {
            "cell_03_final_ids": cell_03.get("final_ids"),
            "row_D_present": "row_D" in (cell_03.get("final_ids") or []),
            "row_D_sparse_rank": next(
                (
                    item["rank"]
                    for item in by_id.get("cell_03_hybrid_none_thr0", {})
                    .get("traces", {})
                    .get("sparse", [])
                    if item["id"] == "row_D"
                ),
                None,
            ),
        },
        "h4": {
            "cell_04_final_ids": cell_04.get("final_ids"),
            "row_B_excluded": "row_B" not in (cell_04.get("final_ids") or []),
            "row_D_excluded": "row_D" not in (cell_04.get("final_ids") or []),
            "cell_04_non_empty": bool(cell_04.get("final_ids")),
            "static_check_artefact": static_check_rel,
        },
        "h5": {
            "cell_05_final_ids": cell_05.get("final_ids"),
            "cell_05_threshold_score_kind": cell_05.get("threshold_score_kind"),
            "cell_05_row_B_survives_reranker_threshold": "row_B"
            in (cell_05.get("final_ids") or []),
            "cell_05_row_D_dropped": "row_D" not in (cell_05.get("final_ids") or []),
            "cell_06_final_ids": cell_06.get("final_ids"),
            "cell_06_threshold_score_kind": cell_06.get("threshold_score_kind"),
            "cell_06_rerank_fallback_reason": cell_06.get("rerank_fallback_reason"),
            "cell_06_fallback_reason_match": cell_06.get("fallback_reason_match"),
            "cell_06_equals_cell_04_outcome": cell_04.get("final_ids") == cell_06.get("final_ids"),
        },
        "exact_match_by_cell": {cid: m["exact_match"] for cid, m in metrics.items()},
    }
