"""Run Experiment 13 (v2.0): HARD_TECHNICAL_THRESHOLD policy calibration.

D18 repair (OpenSpec change ``harden-pipeline-correctness-before-
calibration``, Stage 4 task 4.3.5): the v1 runner forced ``rerank=True``
in every cell, so the swept threshold never routed anything; it also drew
a fresh random sample per (threshold x fraction) cell (unpaired) and had
no reference arms.  v2.0 policy cells call ``search(..., rerank=None)``
with per-cell settings carrying the swept threshold; one fixed query
block per fraction (seeded ``random.Random(f"{SEED}:{fraction}")``) is
reused for every threshold and arm (paired, D18/D16); threshold-
independent reference envelope arms (``reranker_off`` floor,
``reranker_on`` ceiling) run once per fraction; per-query rows carry
``phase`` with warm-up excluded from aggregates; per-cell D13 manifests
pass D14 preflight assertions, controlled variables are pinned across
cells, and plan.json agreement (D15) is enforced before measured work.

Runs through ``omrg.core.retrieval.search`` with an injected store
from ``experiments/_lib/storage.py``; works in local and cloud Chroma
modes.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

THRESHOLDS = [0.1, 0.2, 0.3, 0.5, 0.7]
FRACTIONS = [1.0, 0.9, 0.75, 0.5, 0.25, 0.0]
SEED = 20260629
MIN_QUERIES = 30
WARMUP_QUERIES = 2
EXPERIMENT_ID = "13-hard-technical-threshold-policy-calibration"
PROTOCOL_VERSION = "2.0"

# Mirrors plan.json's ``preflight_assertions``; main aborts on drift (D15).
PLAN_PREFLIGHT_ASSERTIONS: list[dict[str, Any]] = [
    {"manifest_field": "retrieval.top_k", "operator": "eq", "expected": 50},
    {"manifest_field": "embedding.model", "operator": "not_null"},
    {"manifest_field": "vector_store.index_identity", "operator": "not_null"},
]


@dataclass(frozen=True)
class _CellContext:
    """Per-run runtime shared by every cell (store, base settings, facts)."""

    store: Any
    collection_name: str
    base_effective: Any
    facts: dict[str, Any]
    k_values: list[int]
    qrels: dict[str, dict[str, int]]
    qrels_path: Path
    query_set_path: Path
    plan_assertions: list[dict[str, Any]]


def _load_ground_truth(gt_path: Path) -> dict[str, Any]:
    if not gt_path.exists():
        raise SystemExit(f"Ground truth not found: {gt_path}")
    return json.loads(gt_path.read_text(encoding="utf-8"))


def _compute_metrics(
    results: list[dict[str, Any]],
    qrels: dict[str, dict[str, int]],
    k_values: list[int],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for k in k_values:
        hit = 0
        recall_sum = 0.0
        mrr_sum = 0.0
        coverage_count = 0
        for result in results:
            query_id = result["query_id"]
            retrieved_ids = [r["id"] for r in result["retrieved"][:k]]
            relevant = qrels.get(query_id, {})
            relevant_set = {doc_id for doc_id, rel in relevant.items() if rel > 0}
            if not relevant_set:
                continue
            hits_at_k = sum(1 for doc_id in retrieved_ids if doc_id in relevant_set)
            hit += 1 if hits_at_k > 0 else 0
            recall_sum += hits_at_k / len(relevant_set)
            for rank, doc_id in enumerate(retrieved_ids, 1):
                if doc_id in relevant_set:
                    mrr_sum += 1.0 / rank
                    break
            if hits_at_k > 0:
                coverage_count += 1
        n = len(results)
        metrics[f"hit@{k}"] = hit / n if n > 0 else 0.0
        metrics[f"recall@{k}"] = recall_sum / n if n > 0 else 0.0
        metrics[f"mrr@{k}"] = mrr_sum / n if n > 0 else 0.0
        metrics[f"coverage@{k}"] = coverage_count / n if n > 0 else 0.0
    return metrics


def _sample_queries(
    technical: list[dict[str, Any]],
    semantic: list[dict[str, Any]],
    tech_fraction: float,
    min_queries: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Sample a mixed set of queries with the given technical fraction."""
    total = max(min_queries, 60)
    n_tech = int(total * tech_fraction)
    n_sem = total - n_tech

    sampled_tech = rng.sample(technical, min(n_tech, len(technical))) if technical else []
    sampled_sem = rng.sample(semantic, min(n_sem, len(semantic))) if semantic else []

    return sampled_tech + sampled_sem


def build_fixed_blocks(
    technical: list[dict[str, Any]],
    semantic: list[dict[str, Any]],
    fractions: list[float],
    *,
    seed: int,
) -> dict[float, list[dict[str, Any]]]:
    """Build the fixed mixed query block for each technical fraction.

    Each block is drawn once from a per-fraction generator seeded with
    ``f"{seed}:{fraction}"`` and reused verbatim for every threshold and
    arm of that fraction, so comparisons pair by ``query_id`` (D18).
    Pure function: repeated calls return identical blocks.

    Args:
        technical: Identifier-heavy (FreshStack) queries.
        semantic: Qasper semantic queries.
        fractions: Technical-fraction levels to build blocks for.
        seed: Declared experiment seed (``SEED``).

    Returns:
        Mapping of fraction to that fraction's fixed query block.
    """
    blocks: dict[float, list[dict[str, Any]]] = {}
    for fraction in fractions:
        rng = random.Random(f"{seed}:{fraction}")
        blocks[fraction] = _sample_queries(technical, semantic, fraction, MIN_QUERIES, rng)
    return blocks


def build_cell_matrix() -> list[dict[str, Any]]:
    """Return the 42-cell v2.0 matrix matching ``plan.json`` (D15).

    30 policy cells (5 thresholds x 6 fractions) exercise the policy
    resolver with the swept threshold; 12 reference envelope cells
    (6 fractions x {``reranker_off``, ``reranker_on``}) carry no
    threshold factor — they are threshold-independent and deliberately
    not duplicated per threshold (D18).
    """
    cells: list[dict[str, Any]] = []
    for threshold in THRESHOLDS:
        for fraction in FRACTIONS:
            cells.append(
                {
                    "id": f"thr_{threshold}_frac_{fraction}__policy",
                    "factors": {"threshold": threshold, "fraction": fraction, "arm": "policy"},
                }
            )
    for fraction in FRACTIONS:
        cells.append(
            {
                "id": f"thr_ref_frac_{fraction}__off",
                "factors": {"fraction": fraction, "arm": "reranker_off"},
            }
        )
        cells.append(
            {
                "id": f"thr_ref_frac_{fraction}__on",
                "factors": {"fraction": fraction, "arm": "reranker_on"},
            }
        )
    return cells


def threshold_effective_settings(base: Any, threshold: float) -> Any:
    """Overlay the swept HARD_TECHNICAL_THRESHOLD onto base settings.

    Pure helper: the frozen blocks are copied, never mutated, so the base
    instance stays valid for the reference arms.  Applied only to policy
    cells.
    """
    return base.model_copy(
        update={
            "retrieval": base.retrieval.model_copy(update={"hard_technical_threshold": threshold})
        }
    )


def run_query(
    query: str,
    *,
    arm: str,
    collection_name: str,
    store: Any,
    effective: Any,
    top_k: int,
    include_diagnostics: bool = False,
) -> list[dict[str, Any]]:
    """Dispatch one query to the literal ``search`` call site for the arm.

    The three arms map to three literal ``rerank`` keyword values — the
    audit-visible crux of the D18 repair: policy cells pass ``rerank=None``
    so the policy resolver reads the per-cell threshold; the reference arms
    force the reranker off/on to bound the outcome envelope.

    Args:
        query: Query text.
        arm: ``"policy"``, ``"reranker_off"`` or ``"reranker_on"``.
        collection_name: Target collection.
        store: Injected vector store.
        effective: Per-cell ``EffectiveSettings`` (carries the swept
            threshold for policy cells).
        top_k: Result cutoff (``max(k_values)``).
        include_diagnostics: Forwarded to ``search`` so the warm-up probe
            can harvest ``rerank_reason`` for the runtime manifest.

    Returns:
        The search result rows.

    Raises:
        ValueError: On an unknown arm.
    """
    from omrg.core.retrieval import search

    common: dict[str, Any] = {
        "query": query,
        "top_k": top_k,
        "hybrid": False,
        "collection_name": collection_name,
        "effective_settings": effective,
        "store": store,
        "include_diagnostics": include_diagnostics,
    }
    if arm == "policy":
        return search(rerank=None, **common)
    if arm == "reranker_off":
        return search(rerank=False, **common)
    if arm == "reranker_on":
        return search(rerank=True, **common)
    raise ValueError(f"unknown arm {arm!r}")


def _resolve_cell_runtime() -> tuple[Any, str, Any, dict[str, Any]]:
    """Build the shared store, collection name, base settings, and facts.

    Called once per run.  The base settings carry the ambient
    ``hard_technical_threshold`` default (0.3 unless overridden by the
    environment); the reference arms use the base settings directly — the
    threshold is inert under a forced ``rerank=False``/``True`` — while
    policy cells apply :func:`threshold_effective_settings` per swept
    level.  The LlamaIndex global embed model is pinned to the index
    identity so query embeddings match the index.
    """
    from experiments._lib.storage import experiment_storage_config, identity_embed_model

    model = os.getenv("EMBED_MODEL")
    if not model:
        raise SystemExit("EMBED_MODEL is required; set it in .env or the environment")
    chroma_dir = str(SCRIPT_DIR / "output" / "chroma_combined")
    storage = experiment_storage_config(
        experiment_id="exp13",
        corpus="freshstack-qasper-mixed",
        provider="ollama",
        model=model,
        persist_dir=chroma_dir,
    )
    store = storage.build_store()

    from llama_index.core import Settings as LlamaIndexSettings

    from omrg.compose import settings_to_effective
    from omrg.config import Settings
    from omrg.core.vectordb import set_default_store

    settings = Settings()
    # Pin the query embedder to the index identity; ambient Settings()
    # could select a different provider and query with incompatible
    # vectors. Retrieval knobs still come from the ambient settings.
    LlamaIndexSettings.embed_model = identity_embed_model(model)
    set_default_store(store)

    base_effective = settings_to_effective(settings)
    facts: dict[str, Any] = {
        "embed_model": model,
        "chroma_mode": storage.mode,
        "storage_metadata": storage.checkpoint_metadata,
    }
    return store, storage.collection_name, base_effective, facts


def _result_row(
    cell_id: str,
    query: dict[str, Any],
    phase: str,
    latency_ms: float,
    results: list[dict[str, Any]],
    qrels: dict[str, dict[str, int]],
    k_values: list[int],
) -> dict[str, Any]:
    """Build one D16 per-query raw row; aggregates derive from these only.

    Raw retrieval evidence (ids and scores) is persisted per query with
    per-query coverage flags (``None`` when the query has no relevant set).
    """
    retrieved = [{"id": r["id"], "score": r.get("score", 0.0)} for r in results]
    relevant_set = {doc_id for doc_id, rel in qrels.get(query["id"], {}).items() if rel > 0}
    metrics: dict[str, Any] = {
        "query_type": query.get("query_type", "unknown"),
        "retrieved": retrieved,
    }
    for k in k_values:
        if relevant_set:
            covered = any(r["id"] in relevant_set for r in retrieved[:k])
            metrics[f"coverage_at_{k}"] = 1.0 if covered else 0.0
        else:
            metrics[f"coverage_at_{k}"] = None
    return {
        "cell_id": cell_id,
        "query_id": query["id"],
        "phase": phase,
        "latency_ms": latency_ms,
        "metrics": metrics,
    }


def _cell_manifest(
    *,
    cell_id: str,
    arm: str,
    effective: Any,
    top_k: int,
    ctx: _CellContext,
    rerank_policy_reason: str | None,
) -> dict[str, Any]:
    """Build the per-cell D13 runtime manifest with preflight extensions.

    ``retrieval.rerank_requested`` (what the runner passes to ``search``)
    and ``retrieval.hard_technical_threshold`` (the effective swept level;
    the ambient default on reference arms, where it is inert) are injected
    after the standard D13 retrieval block — the former is what
    ``assert_policy_rerank_mode`` reads, the latter records the value the
    policy resolver actually saw.
    """
    from experiments._lib.manifest import build_runtime_manifest

    from omrg.core.vectordb.score import DENSE_SCORE_KIND

    retrieval: dict[str, Any] = {
        "top_k": top_k,
        "fetch_k": None,  # resolver-owned; this design passes no fetch_k override
        "hybrid": False,
        "rrf_k": effective.retrieval.hybrid_rrf_k,
        "threshold": effective.retrieval.hard_technical_threshold,
        "threshold_score_kind": None,
        "rerank_policy_reason": rerank_policy_reason,
    }
    manifest = build_runtime_manifest(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        embedding={
            "requested_provider": "ollama",
            "effective_provider": "ollama",
            "model": ctx.facts["embed_model"],
        },
        vector_store={
            "backend": "chroma",
            "mode": ctx.facts["chroma_mode"],
            "index_identity": ctx.collection_name,
            "score_kind": DENSE_SCORE_KIND,
        },
        retrieval=retrieval,
        qrels_path=ctx.qrels_path,
        query_set_path=ctx.query_set_path,
        extra={"cell_id": cell_id, "arm": arm},
    )
    manifest["retrieval"]["rerank_requested"] = {
        "policy": None,
        "reranker_off": False,
        "reranker_on": True,
    }[arm]
    manifest["retrieval"]["hard_technical_threshold"] = effective.retrieval.hard_technical_threshold
    return manifest


def _run_cell(
    cell: dict[str, Any],
    block: list[dict[str, Any]],
    ctx: _CellContext,
) -> dict[str, Any]:
    """Run one cell: warm-up probe, manifest, preflight, measured rows.

    The first warm-up queries run with ``include_diagnostics=True`` and
    double as the manifest probe that harvests ``rerank_policy_reason``.
    Preflight runs before any measured row is recorded (D14); a
    :class:`~experiments._lib.preflight.PreflightError` propagates so a
    configuration that never took effect is never recorded as data.

    Args:
        cell: Cell dict from :func:`build_cell_matrix`.
        block: The fraction's fixed query block.
        ctx: Shared per-run runtime.

    Returns:
        A ``complete`` cell record built via ``_lib.stats.cell_record``.

    Raises:
        experiments._lib.preflight.PreflightError: On any preflight failure.
    """
    from experiments._lib import preflight
    from experiments._lib import stats as stats_lib

    cell_id = cell["id"]
    arm = cell["factors"]["arm"]
    threshold = cell["factors"].get("threshold")
    effective = (
        threshold_effective_settings(ctx.base_effective, threshold)
        if threshold is not None
        else ctx.base_effective
    )
    top_k = max(ctx.k_values)

    rerank_policy_reason: str | None = None
    warmup_rows: list[dict[str, Any]] = []
    for query in block[:WARMUP_QUERIES]:
        started = time.perf_counter()
        results = run_query(
            query["text"],
            arm=arm,
            collection_name=ctx.collection_name,
            store=ctx.store,
            effective=effective,
            top_k=top_k,
            include_diagnostics=True,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if rerank_policy_reason is None and results:
            rerank_policy_reason = results[0].get("rerank_reason")
        warmup_rows.append(
            _result_row(cell_id, query, "warmup", latency_ms, results, ctx.qrels, ctx.k_values)
        )

    manifest = _cell_manifest(
        cell_id=cell_id,
        arm=arm,
        effective=effective,
        top_k=top_k,
        ctx=ctx,
        rerank_policy_reason=rerank_policy_reason,
    )
    preflight.assert_manifest(manifest, ctx.plan_assertions)
    preflight.assert_no_fallback(manifest)
    if arm == "policy":
        preflight.assert_policy_rerank_mode(manifest)

    measured_rows: list[dict[str, Any]] = []
    for i, query in enumerate(block):
        started = time.perf_counter()
        results = run_query(
            query["text"],
            arm=arm,
            collection_name=ctx.collection_name,
            store=ctx.store,
            effective=effective,
            top_k=top_k,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        measured_rows.append(
            _result_row(cell_id, query, "measured", latency_ms, results, ctx.qrels, ctx.k_values)
        )
        if (i + 1) % 20 == 0:
            print(f"  [{cell_id}] {i + 1}/{len(block)}", flush=True)

    rows = warmup_rows + measured_rows
    stats_lib.validate_per_query_rows(rows)

    derived = [
        {
            "query_id": row["query_id"],
            "query_type": row["metrics"]["query_type"],
            "retrieved": row["metrics"]["retrieved"],
        }
        for row in measured_rows
    ]
    tech = [r for r in derived if r["query_type"] == "technical"]
    sem = [r for r in derived if r["query_type"] == "semantic"]
    metrics_all = _compute_metrics(derived, ctx.qrels, ctx.k_values)
    metrics_technical = _compute_metrics(tech, ctx.qrels, ctx.k_values)
    metrics_semantic = _compute_metrics(sem, ctx.qrels, ctx.k_values)

    print(
        f"[{cell_id}] tech_cov@20={metrics_technical.get('coverage@20', 0):.4f} "
        f"sem_cov@20={metrics_semantic.get('coverage@20', 0):.4f}",
        flush=True,
    )

    return stats_lib.cell_record(
        status="complete",
        cell_id=cell_id,
        arm=arm,
        threshold=threshold,
        fraction=cell["factors"]["fraction"],
        n_queries=len(measured_rows),
        n_technical=len(tech),
        n_semantic=len(sem),
        below_min=len(measured_rows) < MIN_QUERIES,
        metrics_all=metrics_all,
        metrics_technical=metrics_technical,
        metrics_semantic=metrics_semantic,
        per_query=rows,
        manifest=manifest,
    )


def _save_checkpoint(data: dict[str, Any], path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.rename(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Experiment 13 (v2.0, D18 repair)")
    parser.add_argument("--k-values", nargs="+", type=int, default=[5, 10, 20, 50])
    parser.add_argument("--collection-name", default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Protocol/runner agreement is enforced before any measured work (D15).
    from experiments._lib.plan import ExperimentPlan

    plan_path = SCRIPT_DIR / "plan.json"
    if not plan_path.exists():
        raise SystemExit(f"Machine-readable plan missing: {plan_path}")
    plan = ExperimentPlan.from_json(plan_path)
    cells = build_cell_matrix()
    plan.assert_runner_cells(cells)
    plan_assertions = [dict(item) for item in plan.required_manifest_assertions]
    if plan_assertions != PLAN_PREFLIGHT_ASSERTIONS:
        raise SystemExit(
            "plan.json preflight_assertions disagree with the runner's "
            f"PLAN_PREFLIGHT_ASSERTIONS: {plan_assertions} vs {PLAN_PREFLIGHT_ASSERTIONS}"
        )

    # Load FreshStack + Qasper ground truth.
    fs_gt_path = SCRIPT_DIR / "ground-truth.json"
    if not fs_gt_path.exists():
        fs_gt_path = SCRIPT_DIR / "freshstack-qrels.json"
    fs_gt = _load_ground_truth(fs_gt_path) if fs_gt_path.exists() else {"queries": [], "qrels": {}}
    qasper_gt_path = output_dir / "qasper_qrels.json"
    qasper_gt = (
        _load_ground_truth(qasper_gt_path)
        if qasper_gt_path.exists()
        else {"queries": [], "qrels": {}}
    )
    technical_queries = [q for q in fs_gt.get("queries", []) if q.get("is_identifier_heavy", False)]
    semantic_queries = qasper_gt.get("queries", [])
    all_qrels = {**fs_gt.get("qrels", {}), **qasper_gt.get("qrels", {})}

    print(f"Technical queries: {len(technical_queries)}", flush=True)
    print(f"Semantic queries: {len(semantic_queries)}", flush=True)

    # Fixed blocks: drawn once, persisted as a raw artefact, then reused for
    # every threshold and arm (D18 pairing).
    blocks = build_fixed_blocks(technical_queries, semantic_queries, FRACTIONS, seed=SEED)
    query_set_path = output_dir / "fixed_blocks.json"
    _save_checkpoint(
        {
            "seed": SEED,
            "fractions": FRACTIONS,
            "blocks": {str(fraction): blocks[fraction] for fraction in FRACTIONS},
        },
        query_set_path,
    )
    qrels_path = output_dir / "combined_qrels.json"
    _save_checkpoint({"qrels": all_qrels}, qrels_path)

    store, derived_name, base_effective, facts = _resolve_cell_runtime()
    ctx = _CellContext(
        store=store,
        collection_name=args.collection_name or derived_name,
        base_effective=base_effective,
        facts=facts,
        k_values=args.k_values,
        qrels=all_qrels,
        qrels_path=qrels_path,
        query_set_path=query_set_path,
        plan_assertions=plan_assertions,
    )

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    completed_cells: dict[str, dict[str, Any]] = {}
    if args.resume and checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        completed_cells = checkpoint.get("cells", {})
        print(f"Resuming with {len(completed_cells)} completed cells", flush=True)

    from experiments._lib import preflight
    from experiments._lib import stats as stats_lib

    all_records: list[dict[str, Any]] = []
    for cell in cells:
        cell_id = cell["id"]
        if cell_id in completed_cells:
            all_records.append(completed_cells[cell_id])
            continue

        block = blocks[cell["factors"]["fraction"]]
        print(f"\nRunning cell: {cell_id} ({len(block)} queries)", flush=True)
        try:
            record = _run_cell(cell, block, ctx)
        except preflight.PreflightError as exc:
            # A failed preflight is an experimental event, not a data point:
            # record the cell invalid (never numeric) and abort the run.
            invalid = stats_lib.cell_record(
                status="invalid",
                reason=f"preflight failed: {exc}",
                cell_id=cell_id,
                arm=cell["factors"]["arm"],
                threshold=cell["factors"].get("threshold"),
                fraction=cell["factors"]["fraction"],
            )
            completed_cells[cell_id] = invalid
            _save_checkpoint({"cells": completed_cells}, checkpoint_path)
            raise SystemExit(f"cell {cell_id} failed preflight: {exc}") from exc
        all_records.append(record)
        completed_cells[cell_id] = record
        _save_checkpoint({"cells": completed_cells}, checkpoint_path)

    # Controlled variables must hold one observed constant across cells (D14).
    preflight.assert_controlled_constant(
        {
            record["cell_id"]: record["manifest"]
            for record in all_records
            if record.get("status") == "complete"
        },
        ["embedding.model", "vector_store.index_identity", "retrieval.top_k"],
    )

    payload = {
        "experiment": "13-hard-technical-threshold-calibration-2026-06-29",
        "experiment_id": EXPERIMENT_ID,
        "protocol_version": PROTOCOL_VERSION,
        "created_at_unix": time.time(),
        "settings": {
            "k_values": args.k_values,
            "thresholds": THRESHOLDS,
            "fractions": FRACTIONS,
            "arms": ["policy", "reranker_off", "reranker_on"],
            "seed": SEED,
            "min_queries": MIN_QUERIES,
            "warmup_queries": WARMUP_QUERIES,
            "embed_model": facts["embed_model"],
            "chroma_mode": facts["chroma_mode"],
            "collection_name": ctx.collection_name,
            "rerank_fetch_multiplier": 3,
            "rerank_max_fetch": 100,
        },
        "cells": stats_lib.finalise_cells(all_records),
    }

    output_path = output_dir / "eval_results.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {output_path}", flush=True)


if __name__ == "__main__":
    main()
