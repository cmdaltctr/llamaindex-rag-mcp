"""Run Experiment 10b v2: the combined D17 reranker x retrieval x pool factorial.

Merges the 9a-rerun and 10b protocols into ONE paired factorial (design
decision D17 of OpenSpec change ``harden-pipeline-correctness-before-
calibration``, Stage 4 tasks 4.3.1-4.3.4): retrieval mode (dense /
hybrid_bm25) x reranker (off / on) x candidate pool (fetch_k nested
under rerank=on: 50/100/150/200/500).

The v1 runner (preserved as ``run_eval_v1_pre_hardening.py``) executed
dense-only reranker-on cells while the protocol declared a dense x
hybrid matrix, shared no reranker-off controls, and lacked the 150
pool — its results are INVALID for decision evidence.

Key contracts:

- ``run_query`` holds the ONLY pipeline calls in this module: exactly
  four literal-armed call sites dispatched on (retrieval, rerank).  The
  frozen audit test AST-walks this file for the literal hybrid/rerank
  keyword values and requires each collected set to be exactly
  {False, True}; every other argument (fetch_k included) must stay a
  variable.  Warm-up and measured queries share this dispatch.
- ``dense_off`` / ``hybrid_off`` are shared reranker-off ceilings with
  no fetch_k (the pool is meaningless without a reranker): 12 cells,
  not 20.  ``plan.json`` is the machine-readable matrix; agreement is
  asserted at start-up.
- Cells run in a deterministic seeded counterbalanced order so time,
  thermal and cache drift are not confounded with treatment order.
- Each cell builds a D13 runtime manifest and passes the D14 preflight
  (no fallback, plan assertions, fetch_k distinctness by declared pool
  level) BEFORE measured queries; controlled variables are pinned
  across cells after the run.  A failed cell is recorded invalid with
  its reason — never as numeric results.
- Warm-up rows carry phase "warmup" and are excluded from aggregates.

Running at corpus scale is Stage 6 work.  This module is the repaired
harness; it reuses the D17 campaign's immutable LanceDB index (same collection
identity) and ground truth.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from experiments._lib import manifest as manifest_lib  # noqa: E402
from experiments._lib import preflight, stats  # noqa: E402
from experiments._lib.plan import ExperimentPlan  # noqa: E402

# Deterministic schedule seed (paired bootstrap in the summariser reuses it).
SEED = 20260819
# fetch_k pools, nested under rerank=on; 150 is the current post-ADR-021
# production-equivalent pool at top_k=50 (3 x 50).
FETCH_K_POOLS = [50, 100, 150, 200, 500]
MODES = ["dense", "hybrid_bm25"]
PLAN_PATH = SCRIPT_DIR / "plan.json"


def _load_ground_truth(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data


def _parent_id(result: dict[str, Any]) -> str:
    meta = result.get("metadata") or {}
    return str(meta.get("freshstack_id") or result.get("id") or result.get("source") or "")


def _rank_map(parent_ids: list[str]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for rank, parent_id in enumerate(parent_ids, start=1):
        ranks.setdefault(parent_id, rank)
    return ranks


def _dcg(ranking: list[str], nugget_rels: list[set[str]], k: int, alpha: float) -> float:
    import math

    seen = [0 for _ in nugget_rels]
    total = 0.0
    for rank, doc_id in enumerate(ranking[:k], start=1):
        gain = 0.0
        for idx, rels in enumerate(nugget_rels):
            if doc_id in rels:
                gain += (1.0 - alpha) ** seen[idx]
                seen[idx] += 1
        if gain:
            total += gain / math.log2(rank + 1)
    return total


def _alpha_ndcg(
    parent_ids: list[str], nuggets: list[dict[str, Any]], k: int = 10, alpha: float = 0.5
) -> float:
    nugget_rels = [set(n.get("relevant_corpus_ids") or []) for n in nuggets]
    if not nugget_rels:
        return 0.0

    observed = _dcg(parent_ids, nugget_rels, k, alpha)
    candidate_docs = sorted(set().union(*nugget_rels))
    ideal: list[str] = []
    remaining = candidate_docs[:]
    while remaining and len(ideal) < k:
        best_doc = max(remaining, key=lambda doc: _dcg(ideal + [doc], nugget_rels, k, alpha))
        ideal.append(best_doc)
        remaining.remove(best_doc)
    ideal_score = _dcg(ideal, nugget_rels, k, alpha)
    return observed / ideal_score if ideal_score else 0.0


def _metrics_for_query(parent_ids: list[str], query: dict[str, Any]) -> dict[str, Any]:
    ranks = _rank_map(parent_ids)
    relevant = set(query.get("relevant_parent_ids") or [])
    nuggets = query.get("nuggets") or []
    covered = 0
    for nugget in nuggets:
        rels = set(nugget.get("relevant_corpus_ids") or [])
        if rels & set(parent_ids[:20]):
            covered += 1
    hit_ranks = [ranks[doc_id] for doc_id in relevant if doc_id in ranks]
    first_rank = min(hit_ranks) if hit_ranks else None
    return {
        "coverage_at_20": covered / len(nuggets) if nuggets else 0.0,
        "recall_at_50": len(relevant & set(parent_ids[:50])) / len(relevant) if relevant else 0.0,
        "alpha_ndcg_at_10": _alpha_ndcg(parent_ids, nuggets, k=10),
        "hit_at_5": first_rank is not None and first_rank <= 5,
        "hit_at_10": first_rank is not None and first_rank <= 10,
        "mrr_at_10": (1.0 / first_rank) if first_rank is not None and first_rank <= 10 else 0.0,
    }


def build_cell_matrix() -> list[dict[str, Any]]:
    """Return the 12 pre-declared D17 cells (2 shared off-controls + 10 on).

    Off controls carry no ``fetch_k`` (the pool is meaningless without a
    reranker) and are shared across pools rather than duplicated.  This
    is the runner-side twin of ``plan.json``; ``main`` asserts agreement
    via ``ExperimentPlan.assert_runner_cells`` before any cell runs.
    """
    cells: list[dict[str, Any]] = [
        {"id": "dense_off", "factors": {"retrieval": "dense", "rerank": False}},
        {"id": "hybrid_off", "factors": {"retrieval": "hybrid_bm25", "rerank": False}},
    ]
    for mode in MODES:
        mode_short = mode.split("_", 1)[0]
        for pool in FETCH_K_POOLS:
            cells.append(
                {
                    "id": f"{mode_short}_on_{pool}",
                    "factors": {"retrieval": mode, "rerank": True, "fetch_k": pool},
                }
            )
    return cells


def counterbalanced_order(cells: list[dict[str, Any]], iteration: int) -> list[dict[str, Any]]:
    """Return a deterministic seeded shuffle of *cells* (each cell once).

    Counterbalancing decorrelates treatment effects from time, thermal
    drift and cache warmth (D17 template section 10).  Pure function of
    ``(cells, iteration)``; the input list is never mutated.
    """
    ordered = list(cells)
    shuffler = random.Random(SEED + iteration)  # noqa: S311 — fixed schedule, not crypto
    shuffler.shuffle(ordered)
    return ordered


def run_query(
    query: str,
    *,
    top_k: int,
    cell: dict[str, Any],
    collection_name: str,
    store: Any,
    effective_settings: Any,
) -> list[dict[str, Any]]:
    """Dispatch one query to the four-arm literal treatment calls.

    The ONLY pipeline calls in this module; warm-up and measured queries
    share this dispatch.  The frozen audit test requires the literal
    hybrid/rerank keyword sets across this file to be exactly
    {False, True}, so every other argument (fetch_k included) must stay
    a variable.
    """
    from rag_mcp.core.retrieval import search

    factors = cell["factors"]
    if factors["retrieval"] == "dense" and factors["rerank"] is False:
        return search(
            query=query,
            top_k=top_k,
            similarity_threshold=0.0,
            rerank=False,
            hybrid=False,
            collection_name=collection_name,
            store=store,
            effective_settings=effective_settings,
            include_diagnostics=True,
        )
    if factors["retrieval"] == "hybrid_bm25" and factors["rerank"] is False:
        return search(
            query=query,
            top_k=top_k,
            similarity_threshold=0.0,
            rerank=False,
            hybrid=True,
            collection_name=collection_name,
            store=store,
            effective_settings=effective_settings,
            include_diagnostics=True,
        )
    if factors["retrieval"] == "dense":
        return search(
            query=query,
            top_k=top_k,
            similarity_threshold=0.0,
            rerank=True,
            hybrid=False,
            fetch_k=factors["fetch_k"],
            collection_name=collection_name,
            store=store,
            effective_settings=effective_settings,
            include_diagnostics=True,
        )
    return search(
        query=query,
        top_k=top_k,
        similarity_threshold=0.0,
        rerank=True,
        hybrid=True,
        fetch_k=factors["fetch_k"],
        collection_name=collection_name,
        store=store,
        effective_settings=effective_settings,
        include_diagnostics=True,
    )


def _effective_fetch_k(
    top_k: int,
    cell: dict[str, Any],
    store: Any,
    collection_name: str,
    effective_settings: Any,
) -> int:
    """Resolve the effective pool through the production resolver (TDR-005).

    The manifest records the pool that actually ran — clamped to the
    collection size — rather than the requested override.
    """
    from rag_mcp.core.retrieval.policy import _resolve_fetch_k

    chunk_count = store.count(collection_name) if store is not None else 0
    factors = cell["factors"]
    return _resolve_fetch_k(
        top_k,
        factors["rerank"],
        chunk_count,
        effective_settings,
        fetch_k_override=factors.get("fetch_k"),
    )


def _cell_manifest(
    cell: dict[str, Any],
    *,
    top_k: int,
    collection_name: str,
    store: Any,
    effective_settings: Any,
    probe_diagnostics: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Build one D13 runtime manifest for *cell* before its measured work.

    The reranker is observed only for rerank-on cells (off cells have no
    backend by design), via the same settings-driven builder the
    pipeline uses, so a silent backend fallback is caught by
    ``assert_no_fallback``.
    """
    factors = cell["factors"]
    reranker_obj = None
    reranker_requested = None
    if factors["rerank"]:
        from rag_mcp.core.retrieval.backend import build_reranker_from_settings

        reranker_requested = effective_settings.retrieval.rerank_backend
        reranker_obj = build_reranker_from_settings(effective_settings)

    return manifest_lib.build_runtime_manifest(
        experiment_id=ctx["experiment_id"],
        protocol_version=ctx["protocol_version"],
        embedding={
            "requested_provider": "ollama",
            "effective_provider": "ollama",
            "model": ctx["embed_model"],
        },
        vector_store={
            "backend": "lancedb",
            "mode": ctx["storage_mode"],
            "score_kind": "dense_similarity_v1",
        },
        index_identity=collection_name,
        reranker=reranker_obj,
        reranker_requested_backend=reranker_requested,
        retrieval={
            "top_k": top_k,
            "fetch_k": _effective_fetch_k(top_k, cell, store, collection_name, effective_settings),
            "hybrid": factors["retrieval"] == "hybrid_bm25",
            "rrf_k": effective_settings.retrieval.hybrid_rrf_k,
            "threshold": 0.0,
            "threshold_score_kind": probe_diagnostics.get("threshold_score_kind"),
            "rerank_policy_reason": probe_diagnostics.get("rerank_policy_reason"),
        },
        query_set_path=ctx["gt_path"],
        qrels_path=ctx["gt_path"],
        project_root=PROJECT_ROOT,
        extra={"cell_id": cell["id"]},
    )


def _per_query_row(
    cell_id: str,
    query: dict[str, Any],
    phase: str,
    latency_ms: float,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build one D16 per-query row from a dispatched result list."""
    parent_ids = [_parent_id(result) for result in results]
    return {
        "cell_id": cell_id,
        "query_id": query["query_id"],
        "phase": phase,
        "latency_ms": round(latency_ms, 2),
        "metrics": _metrics_for_query(parent_ids, query),
    }


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate measured rows: metric means, hit fractions, latency stats."""
    latencies = [row["latency_ms"] for row in rows]
    n = len(rows)
    agg: dict[str, Any] = {"n": n}
    for key in ("coverage_at_20", "recall_at_50", "alpha_ndcg_at_10", "mrr_at_10"):
        vals = [row["metrics"][key] for row in rows]
        agg[key] = sum(vals) / n if n else 0.0
    for key in ("hit_at_5", "hit_at_10"):
        vals = [row["metrics"][key] for row in rows]
        agg[key] = sum(1 for v in vals if v) / n if n else 0.0
    agg["mean_latency_ms"] = round(statistics.mean(latencies), 2) if latencies else 0.0
    # quantiles() needs at least two data points; a single measured row is
    # its own P95.
    if len(latencies) >= 2:
        agg["p95_latency_ms"] = round(
            statistics.quantiles(latencies, n=100, method="inclusive")[94], 2
        )
    else:
        agg["p95_latency_ms"] = round(latencies[0], 2) if latencies else 0.0
    return agg


def evaluate_cell(
    cell: dict[str, Any],
    queries: list[dict[str, Any]],
    *,
    top_k: int,
    collection_name: str,
    store: Any,
    effective_settings: Any,
    warmup_queries: int = 3,
    run_one: Callable[..., list[dict[str, Any]]] = run_query,
    manifest_ctx: dict[str, Any] | None = None,
    preflight_assertions: list[dict[str, Any]] | None = None,
    observed_fetch_k: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Run one cell end-to-end and return its D16 cell record.

    Warm-up queries run first through the same dispatch, recorded with
    phase "warmup".  With *manifest_ctx*, the D13 manifest and D14
    preflight (no-fallback, plan assertions, incremental fetch_k
    distinctness) gate the measured loop.  Any exception — including
    ``preflight.PreflightError`` — records the cell as invalid with its
    reason; a partial cell is never written as numeric results.
    """
    cell_id = cell["id"]
    manifest: dict[str, Any] | None = None
    try:
        rows: list[dict[str, Any]] = []
        probe_diagnostics: dict[str, Any] = {}
        for query in queries[:warmup_queries]:
            started = time.perf_counter()
            results = run_one(
                query["query"][:4000],
                top_k=top_k,
                cell=cell,
                collection_name=collection_name,
                store=store,
                effective_settings=effective_settings,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            if not probe_diagnostics and results:
                first = results[0]
                probe_diagnostics = {
                    "threshold_score_kind": first.get("threshold_score_kind"),
                    "rerank_policy_reason": first.get("rerank_reason"),
                }
            rows.append(_per_query_row(cell_id, query, "warmup", latency_ms, results))

        if manifest_ctx is not None:
            manifest = _cell_manifest(
                cell,
                top_k=top_k,
                collection_name=collection_name,
                store=store,
                effective_settings=effective_settings,
                probe_diagnostics=probe_diagnostics,
                ctx=manifest_ctx,
            )
            preflight.assert_no_fallback(manifest)
            preflight.assert_manifest(manifest, preflight_assertions or [])
            if observed_fetch_k is not None and cell["factors"]["rerank"]:
                # Keyed by DECLARED pool level: both modes share each level
                # by design, so a collision means two declared levels
                # collapsed onto one effective value — the D14 abort case.
                declared = cell["factors"]["fetch_k"]
                observed_fetch_k[f"pool_{declared}"] = manifest["retrieval"]["fetch_k"]
                preflight.assert_distinct_values(observed_fetch_k, "retrieval.fetch_k")

        for index, query in enumerate(queries, start=1):
            started = time.perf_counter()
            results = run_one(
                query["query"][:4000],
                top_k=top_k,
                cell=cell,
                collection_name=collection_name,
                store=store,
                effective_settings=effective_settings,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            rows.append(_per_query_row(cell_id, query, "measured", latency_ms, results))
            if index % 25 == 0 or index == len(queries):
                print(f"    {cell_id}: {index}/{len(queries)} queries", flush=True)

        stats.validate_per_query_rows(rows)
        measured = [row for row in rows if row["phase"] == "measured"]
        return stats.cell_record(
            status="complete",
            cell_id=cell_id,
            factors=cell["factors"],
            per_query=rows,
            aggregate=_aggregate_rows(measured),
            manifest=manifest,
        )
    except Exception as exc:
        # A failed cell is an experimental event, not a data point: record
        # the reason and never invent numeric failure values (D16).
        return stats.cell_record(status="invalid", reason=str(exc), cell_id=cell_id)


def _resolve_runtime(store_dir: Path) -> tuple[Any, str, str, Any]:
    """Resolve the immutable LanceDB index store once for the whole run.

    Returns ``(store, collection_name, storage_mode, effective_settings)``.
    The query embedder is pinned to the index identity so ambient
    settings cannot query it with incompatible vectors; settings resolve
    once at this boundary (ADR-037) and are injected into every call.
    """
    from experiments._lib.storage import experiment_storage_config, identity_embed_model

    model = os.getenv("EMBED_MODEL")
    if not model:
        raise SystemExit("EMBED_MODEL is required; set it in .env or the environment")
    storage = experiment_storage_config(
        experiment_id="exp10b",
        corpus="freshstack-langchain-seed-20260530",
        provider="ollama",
        model=model,
        persist_dir=str(store_dir),
        backend="lancedb",
    )
    store = storage.build_store()

    from llama_index.core import Settings as LlamaIndexSettings

    from rag_mcp.core.settings import resolve_effective_settings
    from rag_mcp.core.vectordb import set_default_store

    LlamaIndexSettings.embed_model = identity_embed_model(model)
    set_default_store(store)
    effective_settings = resolve_effective_settings(None)

    try:
        from rag_mcp.core.retrieval.dense import _cached_query_embedding

        _cached_query_embedding.cache_clear()
    except Exception:
        pass
    return store, storage.collection_name, storage.mode, effective_settings


def _save_checkpoint(path: Path, cells: list[dict[str, Any]]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"cells": cells}, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Experiment 10b v2 (combined D17 factorial, protocol 2.0)"
    )
    parser.add_argument("--k-values", nargs="+", type=int, default=[5, 10, 20, 50])
    parser.add_argument("--warmup-queries", type=int, default=3)
    parser.add_argument("--limit-queries", type=int, default=None)
    parser.add_argument(
        "--order-iteration",
        type=int,
        default=0,
        help="counterbalance rotation index for the cell execution order",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Plan/runner agreement is itself a preflight: the declared 12-cell
    # matrix is the experiment; a differing runner matrix aborts the run.
    plan = ExperimentPlan.from_json(PLAN_PATH)
    cells = build_cell_matrix()
    plan.assert_runner_cells(cells)

    gt_path = SCRIPT_DIR / "ground-truth.json"
    ground_truth = _load_ground_truth(gt_path)
    queries = ground_truth["queries"][: args.limit_queries]
    top_k = max(args.k_values)
    print(f"Loaded {len(queries)} queries; {len(cells)} cells; top_k={top_k}", flush=True)

    store_dir = output_dir / "lancedb_dense"
    if not store_dir.exists():
        raise SystemExit(f"Missing LanceDB index: {store_dir}")
    store, collection_name, storage_mode, effective_settings = _resolve_runtime(store_dir)
    embed_model = os.getenv("EMBED_MODEL")

    manifest_ctx = {
        "experiment_id": plan.experiment_id,
        "protocol_version": plan.protocol_version,
        "embed_model": embed_model,
        "storage_mode": storage_mode,
        "gt_path": gt_path,
    }
    observed_fetch_k: dict[str, int] = {}

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    completed_cells: list[dict[str, Any]] = []
    completed_keys: set[str] = set()
    if args.resume and checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        completed_cells = checkpoint.get("cells", [])
        completed_keys = {str(cell["cell_id"]) for cell in completed_cells}
        print(f"Resuming with {len(completed_keys)} recorded cells", flush=True)

    for cell in counterbalanced_order(cells, args.order_iteration):
        if cell["id"] in completed_keys:
            print(f"Skipping recorded cell: {cell['id']}", flush=True)
            continue

        print(f"\nEvaluating cell {cell['id']} (factors: {cell['factors']})", flush=True)
        record = evaluate_cell(
            cell,
            queries,
            top_k=top_k,
            collection_name=collection_name,
            store=store,
            effective_settings=effective_settings,
            warmup_queries=args.warmup_queries,
            run_one=run_query,
            manifest_ctx=manifest_ctx,
            preflight_assertions=list(plan.required_manifest_assertions),
            observed_fetch_k=observed_fetch_k,
        )
        completed_cells.append(record)
        completed_keys.add(cell["id"])
        _save_checkpoint(checkpoint_path, completed_cells)
        if record["status"] != "complete":
            print(
                f"Cell {cell['id']} recorded as {record['status']}: {record['reason']}", flush=True
            )

    manifests_by_cell = {
        str(record["cell_id"]): record["manifest"]
        for record in completed_cells
        if record.get("manifest") is not None
    }
    # Controlled-variable pinning (D14): a controlled field that varies
    # between cells was manipulated, and one never observed is absent.
    # A violation aborts the run — the checkpointed cells stay on disk.
    preflight.assert_controlled_constant(
        manifests_by_cell,
        [
            "embedding.model",
            "vector_store.index_identity",
            "retrieval.top_k",
            "retrieval.threshold",
        ],
    )

    payload = {
        "experiment": plan.experiment_id,
        "protocol_version": plan.protocol_version,
        "created_at_unix": time.time(),
        "hardware": {"platform": platform.platform()},
        "settings": {
            "k_values": args.k_values,
            "top_k_requested": top_k,
            "warmup_queries": args.warmup_queries,
            "order_iteration": args.order_iteration,
            "seed": SEED,
            "fetch_k_pools": FETCH_K_POOLS,
            "modes": MODES,
            "embed_model": embed_model,
        },
        "cells": stats.finalise_cells(completed_cells),
        "manifests_by_cell": manifests_by_cell,
    }

    output_path = output_dir / "eval_results.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {output_path}", flush=True)


if __name__ == "__main__":
    main()
