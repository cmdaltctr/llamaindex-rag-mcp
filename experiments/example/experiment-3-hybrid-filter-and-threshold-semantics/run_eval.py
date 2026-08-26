"""Run Experiment 3 (v1.0): hybrid filter and threshold semantics gate.

Deterministic correctness experiment (protocol.md §1-20).  One fixed
query runs against a five-row synthetic fixture (pre-registered in
``fixtures/manifest.json``) through the production ``search()`` path in
``src/rag_mcp/core/retrieval/pipeline.py``.  Manipulated factors: mode
{dense, hybrid_bm25} × filter {none, category operators} × threshold
{0.0, 0.3} × rerank {off, fake-success double, fake-failure double}.
Assertions are exact, per protocol §15; branch-level candidate traces
are saved so a leaked row is attributable to dense, sparse or fusion.

Seams (no production edits): fixture vectors enter the store through
``ChromaVectorStore.upsert_precomputed``; the query embedding is
returned by an injected ``FixtureEmbedModel`` pinned to the LlamaIndex
global ``Settings.embed_model`` (the seam ``compose`` uses); the
reranker doubles are injected through ``search(reranker=...)`` — the
dependency-injection seam the pipeline already exposes.

Run: ``uv run --no-sync python experiments/example/experiment-3-hybrid-filter-and-threshold-semantics/run_eval.py``
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from harness import (  # noqa: E402
    FakeFailureReranker,
    FakeSuccessReranker,
    FixtureEmbedModel,
    branch_traces,
    build_cell_matrix,
    compose_final,
    hypothesis_inputs,
)

EXPERIMENT_ID = "3-hybrid-filter-and-threshold-semantics"
PROTOCOL_VERSION = "1.0"
COLLECTION_NAME = "exp3_hybrid_filter_threshold_fixture"
FIXTURE_MANIFEST = SCRIPT_DIR / "fixtures" / "manifest.json"
QUERIES_PATH = SCRIPT_DIR / "fixtures" / "queries.json"
QRELS_PATH = SCRIPT_DIR / "fixtures" / "qrels.json"
STATIC_CHECK_REL = "output/static_check/threshold_application_sites.json"

# Mirrors plan.json's ``preflight_assertions``; main aborts on drift (D15).
PLAN_PREFLIGHT_ASSERTIONS: list[dict[str, Any]] = [
    {"manifest_field": "retrieval.top_k", "operator": "eq", "expected": 5},
    {"manifest_field": "retrieval.fetch_k", "operator": "eq", "expected": 5},
    {"manifest_field": "retrieval.rrf_k", "operator": "eq", "expected": 60},
    {"manifest_field": "retrieval.threshold", "operator": "in", "expected": [0.0, 0.3]},
    {
        "manifest_field": "retrieval.threshold_score_kind",
        "operator": "in",
        "expected": ["dense_similarity_v1", "reranker_sigmoid_v1"],
    },
    {"manifest_field": "vector_store.backend", "operator": "eq", "expected": "chroma"},
    {"manifest_field": "vector_store.mode", "operator": "eq", "expected": "ephemeral"},
    {
        "manifest_field": "vector_store.score_kind",
        "operator": "eq",
        "expected": "dense_similarity_v1",
    },
    {"manifest_field": "vector_store.index_identity", "operator": "not_null"},
    {
        "manifest_field": "embedding.requested_provider",
        "operator": "eq",
        "expected": "precomputed_fixture",
    },
    {
        "manifest_field": "embedding.effective_provider",
        "operator": "eq",
        "expected": "precomputed_fixture",
    },
    {
        "manifest_field": "embedding.model",
        "operator": "eq",
        "expected": "fixture-fake-embed-model-v1",
    },
    {"manifest_field": "sparse.requested_backend", "operator": "eq", "expected": "bm25"},
    {"manifest_field": "corpus_identity", "operator": "not_null"},
    {"manifest_field": "query_set_identity", "operator": "not_null"},
    {"manifest_field": "qrels_identity", "operator": "not_null"},
    {"manifest_field": "repo_commit", "operator": "not_null"},
    {"manifest_field": "dependency_lock_hash", "operator": "not_null"},
]


# ── Runtime assembly ──────────────────────────────────────────────────


def _resolve_runtime(fixture: dict[str, Any]) -> dict[str, Any]:
    """Build the ephemeral store, fixture rows, and pinned settings.

    The store is an in-memory ChromaDB client wrapped by the production
    :class:`ChromaVectorStore` with no embedding identity (direct-call
    path), so nothing is stamped or enforced beyond the fixture bytes.
    Controlled retrieval knobs are pinned on the ``EffectiveSettings``
    copy so ambient environment variables cannot drift the run.
    """
    import chromadb
    from llama_index.core import Settings as LlamaIndexSettings

    from rag_mcp.compose import settings_to_effective
    from rag_mcp.config import Settings
    from rag_mcp.core.vectordb.chroma import ChromaVectorStore

    client = chromadb.EphemeralClient(settings=chromadb.Settings(anonymized_telemetry=False))
    store = ChromaVectorStore(client=client)
    store.create_collection(COLLECTION_NAME)
    rows = fixture["rows"]
    store.upsert_precomputed(
        collection_name=COLLECTION_NAME,
        ids=[row["id"] for row in rows],
        documents=[row["text"] for row in rows],
        metadatas=[dict(row["metadata"]) for row in rows],
        embeddings=[list(row["vector"]) for row in rows],
    )

    LlamaIndexSettings.embed_model = FixtureEmbedModel(fixture["query"]["vector"])

    base = settings_to_effective(Settings())
    effective = base.model_copy(
        update={
            "retrieval": base.retrieval.model_copy(
                update={
                    "hybrid_sparse_backend": "bm25",
                    "hybrid_rrf_k": int(fixture["constants"]["rrf_k"]),
                    "top_k": int(fixture["constants"]["top_k"]),
                    "similarity_threshold": 0.0,
                    "hybrid_enabled": False,
                    "rerank_enabled": False,
                }
            )
        }
    )
    # The store's paged reads consult the composition-root default for
    # the scan page size; install our pinned instance the same way the
    # composition root would (AGENTS.md gotcha 8a).
    from rag_mcp.core.settings import set_default_effective_settings

    set_default_effective_settings(effective)
    return {"store": store, "effective": effective}


def _fixture_sanity(fixture: dict[str, Any], store: Any) -> dict[str, Any]:
    """Abort (protocol §13) unless the store reproduces fixture geometry.

    Checks the raw dense branch: exact ID ordering, monotone strictly
    decreasing canonical scores, per-row band membership under either L2
    reporting convention, and the 0.3 threshold membership bands.
    """
    from rag_mcp.core.retrieval.dense import _dense_query_rows

    rows = _dense_query_rows(store, COLLECTION_NAME, fixture["query"]["text"], 5, None)
    observed_order = [row["id"] for row in rows]
    expected_order = fixture["expectations"]["dense_order"]
    if observed_order != expected_order:
        raise SystemExit(
            f"fixture sanity abort (§13): dense ordering {observed_order} != "
            f"precomputed expectation {expected_order}"
        )

    bands = fixture["expectations"]["dense_bands"]
    membership = fixture["expectations"]["dense_threshold_membership"]
    threshold = float(membership["threshold"])
    # Bands tolerate ChromaDB's float32 distance arithmetic (~1e-8);
    # the analytic band gaps are >= 0.045, six orders wider.
    tolerance = 1e-6
    problems: list[str] = []
    convention = "unknown"
    previous: float | None = None
    for row in rows:
        doc_id = row["id"]
        score = float(row["score"])
        band = bands[doc_id]
        if not (band["band_min"] - tolerance <= score <= band["band_max"] + tolerance):
            problems.append(f"{doc_id} score {score!r} outside band {band}")
        if previous is not None and not (score < previous):
            problems.append(f"{doc_id} score {score!r} not strictly below previous")
        previous = score
        expected_qualifies = doc_id in membership["qualifying"]
        if (score >= threshold) != expected_qualifies:
            problems.append(f"{doc_id} threshold membership mismatch at {threshold}")
        if abs(score - band["band_squared_convention"]) <= tolerance:
            convention = "squared_l2"
        elif abs(score - band["band_unsquared_convention"]) <= tolerance:
            convention = "unsquared_l2"
    if problems:
        raise SystemExit("fixture sanity abort (§13): " + "; ".join(problems))

    return {
        "observed_dense_scores": {row["id"]: float(row["score"]) for row in rows},
        "convention_detected": convention,
        "score_kind": rows[0]["score_kind"],
    }


def _probe_fake(reranker: Any, mode: str) -> dict[str, Any]:
    """Assert the intended fake mode is armed before measured work (§12)."""
    probe_row = {"id": "row_A", "text": "probe", "score": 0.5}
    out = reranker.rerank("probe", [dict(probe_row)], top_k=1)
    if mode == "fake_success":
        armed = (
            bool(out)
            and out[0]["score"] == 0.5
            and out[0].get("_reranked") is True
            and reranker.last_failure_reason is None
        )
    else:
        armed = (
            bool(out)
            and out[0]["score"] == 0.5
            and out[0].get("_reranked") is False
            and reranker.last_failure_reason is not None
        )
    if not armed:
        raise SystemExit(f"fake reranker double for mode {mode!r} is not armed")
    return {"mode": mode, "armed": True}


def run_query(
    query_text: str,
    *,
    mode: str,
    rerank: str,
    threshold: float,
    metadata_filter: dict[str, Any] | None,
    collection_name: str,
    store: Any,
    effective: Any,
    top_k: int,
    fetch_k: int,
    reranker: Any = None,
) -> list[dict[str, Any]]:
    """Dispatch to the literal ``search()`` call site for the cell's arm.

    Every manipulated lever is a literal keyword argument at a real call
    site — dense forces ``hybrid=False, rerank=False``; hybrid cells pin
    ``hybrid=True`` with the arm's rerank value; fake doubles inject
    through the ``reranker=`` seam.
    """
    from rag_mcp.core.retrieval import search

    common: dict[str, Any] = {
        "query": query_text,
        "top_k": top_k,
        "fetch_k": fetch_k,
        "similarity_threshold": threshold,
        "metadata_filter": metadata_filter,
        "collection_name": collection_name,
        "effective_settings": effective,
        "store": store,
        "include_diagnostics": True,
    }
    if mode == "dense":
        return search(hybrid=False, rerank=False, **common)
    if rerank == "off":
        return search(hybrid=True, rerank=False, **common)
    if rerank == "fake_success":
        return search(hybrid=True, rerank=True, reranker=reranker, **common)
    if rerank == "fake_failure":
        return search(hybrid=True, rerank=True, reranker=reranker, **common)
    raise ValueError(f"unknown arm {mode}/{rerank!r}")


# ── Per-cell manifest + execution ─────────────────────────────────────


def _cell_manifest(
    *,
    cell: dict[str, Any],
    runtime: dict[str, Any],
    threshold: float,
    threshold_score_kind: str | None,
    rerank_reason: str | None,
) -> dict[str, Any]:
    """Build the per-cell D13 runtime manifest with preflight extensions."""
    from experiments._lib.manifest import build_runtime_manifest

    from rag_mcp.core.vectordb.score import DENSE_SCORE_KIND

    mode = cell["factors"]["mode"]
    rerank = cell["factors"]["rerank"]
    retrieval: dict[str, Any] = {
        "top_k": 5,
        "fetch_k": 5,
        "hybrid": mode == "hybrid_bm25",
        "rrf_k": runtime["effective"].retrieval.hybrid_rrf_k,
        "threshold": threshold,
        "threshold_score_kind": threshold_score_kind,
        "rerank_policy_reason": rerank_reason,
    }
    manifest = build_runtime_manifest(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        embedding={
            "requested_provider": "precomputed_fixture",
            "effective_provider": "precomputed_fixture",
            "model": "fixture-fake-embed-model-v1",
        },
        vector_store={
            "backend": "chroma",
            "mode": "ephemeral",
            "index_identity": COLLECTION_NAME,
            "score_kind": DENSE_SCORE_KIND,
        },
        sparse={
            "requested_backend": runtime["effective"].retrieval.hybrid_sparse_backend,
            "effective_backend": "bm25" if mode == "hybrid_bm25" else None,
            "cache_namespace": f"ephemeral:{COLLECTION_NAME}" if mode == "hybrid_bm25" else None,
        },
        reranker=runtime.get("reranker"),
        reranker_requested_backend=runtime.get("reranker_requested_backend"),
        retrieval=retrieval,
        corpus_path=FIXTURE_MANIFEST,
        query_set_path=QUERIES_PATH,
        qrels_path=QRELS_PATH,
        index_identity=COLLECTION_NAME,
        extra={"cell_id": cell["id"]},
    )
    manifest["retrieval"]["rerank_requested"] = {
        "off": False,
        "fake_success": True,
        "fake_failure": True,
    }[rerank]
    manifest["retrieval"]["mode"] = mode
    return manifest


def _assert_cell_preflight(manifest: dict[str, Any], cell: dict[str, Any]) -> None:
    """Cell-type-specific asserts beyond the shared plan assertions (§12)."""
    from experiments._lib.preflight import (
        PreflightError,
        assert_manifest,
        assert_no_fallback,
        manifest_field,
    )

    assert_manifest(manifest, PLAN_PREFLIGHT_ASSERTIONS)
    assert_no_fallback(manifest)
    mode = cell["factors"]["mode"]
    rerank = cell["factors"]["rerank"]
    failures: list[str] = []
    if mode == "hybrid_bm25":
        if manifest_field(manifest, "sparse.effective_backend") != "bm25":
            failures.append(
                "hybrid cell must run the in-process BM25 sparse backend (native is an abort)"
            )
        if manifest_field(manifest, "sparse.cache_namespace") is None:
            failures.append("hybrid cell must record the sparse cache namespace")
    elif manifest_field(manifest, "sparse.effective_backend") is not None:
        failures.append("dense cell must leave the sparse branch inactive")
    if rerank == "off":
        if manifest_field(manifest, "reranker.effective_backend") is not None:
            failures.append(
                "rerank-off cell must not activate any reranker (real model selected → abort §13)"
            )
    else:
        expected = {
            "fake_success": "FakeSuccessReranker",
            "fake_failure": "FakeFailureReranker",
        }[rerank]
        if manifest_field(manifest, "reranker.effective_backend") != expected:
            failures.append(
                f"{rerank} cell must run the {expected} double (real model selected → abort §13)"
            )
        if manifest_field(manifest, "reranker.model") is None:
            failures.append("reranker double must record its model identity")
    if failures:
        raise PreflightError("\n".join(failures))


def _run_cell(
    cell: dict[str, Any],
    fixture: dict[str, Any],
    qrels: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    """Run one cell: probe doubles, trace branches, measure, assert exactly.

    Exact assertion failures against the pre-registered qrels are
    recorded as ``exact_match=0`` measurements (the cell still
    completes — the observation is the finding); preflight failures and
    fixture-validity failures abort per protocol §13.
    """
    from experiments._lib import stats as stats_lib

    from rag_mcp.core.retrieval.filters import matches_metadata_filter

    cell_id = cell["id"]
    factors = cell["factors"]
    mode, rerank, threshold = factors["mode"], factors["rerank"], factors["threshold"]
    metadata_filter = fixture["filters"][factors["filter"]]
    query_text = fixture["query"]["text"]
    top_k = int(fixture["constants"]["top_k"])
    fetch_k = int(fixture["constants"]["fetch_k"])

    runtime["reranker"] = None
    runtime["reranker_requested_backend"] = None
    if rerank == "fake_success":
        runtime["reranker"] = FakeSuccessReranker(fixture["fake_reranker_scores"])
        runtime["reranker_requested_backend"] = "FakeSuccessReranker"
    elif rerank == "fake_failure":
        runtime["reranker"] = FakeFailureReranker(
            "fake failure double: simulated reranker backend load failure"
        )
        runtime["reranker_requested_backend"] = "FakeFailureReranker"
    fake_probe = (
        _probe_fake(runtime["reranker"], rerank)
        if rerank != "off"
        else {"mode": "off", "armed": True}
    )

    started = time.perf_counter()
    results = run_query(
        query_text,
        mode=mode,
        rerank=rerank,
        threshold=threshold,
        metadata_filter=metadata_filter,
        collection_name=COLLECTION_NAME,
        store=runtime["store"],
        effective=runtime["effective"],
        top_k=top_k,
        fetch_k=fetch_k,
        reranker=runtime["reranker"],
    )
    latency_ms = (time.perf_counter() - started) * 1000.0

    rerank_reason = results[0].get("rerank_reason") if results else None
    observed_threshold_kind = (
        results[0].get("threshold_score_kind") if results else "dense_similarity_v1"
    )

    manifest = _cell_manifest(
        cell=cell,
        runtime=runtime,
        threshold=threshold,
        threshold_score_kind=observed_threshold_kind,
        rerank_reason=rerank_reason,
    )
    _assert_cell_preflight(manifest, cell)

    trace = branch_traces(
        fixture,
        mode=mode,
        rerank=rerank,
        threshold=threshold,
        metadata_filter=metadata_filter,
        store=runtime["store"],
        collection_name=COLLECTION_NAME,
        query_text=query_text,
        fetch_k=fetch_k,
    )

    expected = qrels["cells"][cell_id]
    observed_ids = [str(row["id"]) for row in results]
    exact_ids = observed_ids == expected["final_ids"]
    exact_kinds = all(row.get("score_kind") == expected["score_kind"] for row in results)
    exact_scores = True
    if expected.get("fused_scores") is not None:
        for row in results:
            analytic = expected["fused_scores"].get(str(row["id"]))
            if (
                analytic is None
                or abs(float(row.get("fused_score", row["score"])) - analytic) > 1e-12
            ):
                exact_scores = False
    if expected.get("reranker_scores") is not None:
        for row in results:
            analytic = expected["reranker_scores"].get(str(row["id"]))
            if analytic is None or abs(float(row["score"]) - analytic) > 1e-12:
                exact_scores = False

    composed = compose_final(
        fixture, trace=trace, mode=mode, rerank=rerank, threshold=threshold, top_k=top_k
    )
    composed_match = [row["id"] for row in composed] == observed_ids

    forbidden = set(qrels["forbidden_rows"])
    final_leaks = sum(
        1
        for row in results
        if not matches_metadata_filter(row.get("metadata", {}), metadata_filter)
        or str(row["id"]) in forbidden
    )
    failure_reason = (
        getattr(runtime["reranker"], "last_failure_reason", None)
        if rerank == "fake_failure"
        else None
    )
    fallback_reason_match = rerank_reason == failure_reason if rerank == "fake_failure" else True

    row = {
        "cell_id": cell_id,
        "query_id": fixture["query"]["id"],
        "phase": "measured",
        "latency_ms": latency_ms,
        "metrics": {
            "final_ids": observed_ids,
            "final_scores": [float(row["score"]) for row in results],
            "final_score_kind": results[0].get("score_kind") if results else None,
            "threshold_score_kind": observed_threshold_kind,
            "rerank_reason": rerank_reason,
            "rerank_fallback_reason": failure_reason,
            "fallback_reason_match": fallback_reason_match,
            "n_final": len(results),
            "forbidden_leak_count": final_leaks,
            "dense_branch_filter_violations": trace["dense_branch_filter_violations"],
            "sparse_branch_filter_violations": trace["sparse_branch_filter_violations"],
            "exact_ids_match": float(exact_ids),
            "exact_score_kind_match": float(exact_kinds),
            "exact_scores_match": float(exact_scores),
            "composed_trace_match": float(composed_match),
            "exact_match": float(exact_ids and exact_kinds and exact_scores and composed_match),
        },
    }
    stats_lib.validate_per_query_rows([row])

    return stats_lib.cell_record(
        status="complete",
        cell_id=cell_id,
        factors=dict(factors),
        fake_probe=fake_probe,
        per_query=[row],
        observed=[{k: v for k, v in r.items() if k != "metadata"} for r in results],
        traces=trace,
        manifest=manifest,
    )


# ── Orchestration ─────────────────────────────────────────────────────

_VOLATILE_KEYS = frozenset({"timestamp_utc", "created_at_unix", "latency_ms"})


def _canonicalise(value: Any) -> Any:
    """Drop wall-clock and latency fields for the byte-identical rerun proof."""
    if isinstance(value, dict):
        return {k: _canonicalise(v) for k, v in value.items() if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_canonicalise(item) for item in value]
    return value


def _save_json(payload: Any, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.rename(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Experiment 3 (v1.0)")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    from experiments._lib import preflight
    from experiments._lib import stats as stats_lib
    from experiments._lib.plan import ExperimentPlan

    plan = ExperimentPlan.from_json(SCRIPT_DIR / "plan.json")
    cells = build_cell_matrix()
    plan.assert_runner_cells(cells)
    # Compare assertion semantics (field/operator/expected); the plan's
    # ``reason`` strings are documentation, not part of the contract.
    plan_assertions = [dict(item) for item in plan.required_manifest_assertions]

    def _semantics(assertions: list[dict[str, Any]]) -> list[tuple[str, str, Any]]:
        return [
            (str(a["manifest_field"]), str(a["operator"]), a.get("expected")) for a in assertions
        ]

    if _semantics(plan_assertions) != _semantics(PLAN_PREFLIGHT_ASSERTIONS):
        raise SystemExit(
            "plan.json preflight_assertions disagree with the runner's "
            f"PLAN_PREFLIGHT_ASSERTIONS: {plan_assertions} vs {PLAN_PREFLIGHT_ASSERTIONS}"
        )

    fixture = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
    qrels = json.loads(QRELS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    if queries["queries"][0]["text"] != fixture["query"]["text"]:
        raise SystemExit("queries.json and fixture manifest disagree on the query text")

    runtime = _resolve_runtime(fixture)
    sanity = _fixture_sanity(fixture, runtime["store"])
    print(
        f"sanity: dense ordering + bands OK (convention={sanity['convention_detected']})",
        flush=True,
    )

    output_dir = SCRIPT_DIR / "output" / "cells"
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = SCRIPT_DIR / "checkpoint.json"
    completed: dict[str, dict[str, Any]] = {}
    if args.resume and checkpoint_path.exists():
        completed = json.loads(checkpoint_path.read_text(encoding="utf-8")).get("cells", {})
        print(f"Resuming with {len(completed)} completed cells", flush=True)

    records: list[dict[str, Any]] = []
    for cell in cells:
        cell_id = cell["id"]
        if cell_id in completed:
            records.append(completed[cell_id])
            continue
        print(f"Running cell: {cell_id}", flush=True)
        try:
            record = _run_cell(cell, fixture, qrels, runtime)
        except preflight.PreflightError as exc:
            invalid = stats_lib.cell_record(
                status="invalid", reason=f"preflight failed: {exc}", cell_id=cell_id
            )
            completed[cell_id] = invalid
            _save_json({"cells": completed}, checkpoint_path)
            raise SystemExit(f"cell {cell_id} failed preflight: {exc}") from exc
        records.append(record)
        completed[cell_id] = record
        _save_json({"cells": completed}, checkpoint_path)
        _save_json(record, output_dir / f"{cell_id}.json")
        metrics = record["per_query"][0]["metrics"]
        print(f"  final={metrics['final_ids']} exact_match={metrics['exact_match']}", flush=True)

    preflight.assert_controlled_constant(
        {rec["cell_id"]: rec["manifest"] for rec in records if rec["status"] == "complete"},
        [
            "embedding.model",
            "vector_store.index_identity",
            "corpus_identity",
            "retrieval.rrf_k",
            "retrieval.top_k",
            "retrieval.fetch_k",
        ],
    )

    payload = {
        "experiment": "experiment-3-hybrid-filter-and-threshold-semantics",
        "experiment_id": EXPERIMENT_ID,
        "protocol_version": PROTOCOL_VERSION,
        "created_at_unix": time.time(),
        "sanity": sanity,
        "hypotheses": hypothesis_inputs(records, qrels, static_check_rel=STATIC_CHECK_REL),
        "cells": stats_lib.finalise_cells(records),
    }
    _save_json(payload, SCRIPT_DIR / "results.raw.json")
    _save_json(_canonicalise(payload), SCRIPT_DIR / "results.canonical.json")
    print(f"Results saved to {SCRIPT_DIR / 'results.raw.json'}", flush=True)


if __name__ == "__main__":
    main()
