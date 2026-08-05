"""Run Experiment 13: HARD_TECHNICAL_THRESHOLD calibration.

Sweeps HARD_TECHNICAL_THRESHOLD × technical-query fraction on a mixed
corpus (FreshStack technical + Qasper semantic).
"""

# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (rag_mcp.ingestion, rag_mcp.retrieval, rag_mcp.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.


from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

THRESHOLDS = [0.1, 0.2, 0.3, 0.5, 0.7]
FRACTIONS = [1.0, 0.9, 0.75, 0.5, 0.25, 0.0]
SEED = 20260629
MIN_QUERIES = 30


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


def _setup_environment(threshold: float) -> None:
    from rag_mcp import config

    chroma_dir = str(SCRIPT_DIR / "output" / "chroma_combined")
    config.CHROMA_PERSIST_DIR = chroma_dir
    config.HYBRID_ENABLED = False
    config.RERANK_ENABLED = True
    config.RERANK_FETCH_MULTIPLIER = 3
    config.RERANK_MAX_FETCH = 100
    config.HARD_TECHNICAL_THRESHOLD = threshold


def _run_cell(
    cell_name: str,
    threshold: float,
    tech_fraction: float,
    queries: list[dict[str, Any]],
    qrels: dict[str, dict[str, int]],
    k_values: list[int],
    collection_name: str,
) -> dict[str, Any]:
    from rag_mcp import retrieval

    _setup_environment(threshold)

    results: list[dict[str, Any]] = []
    for i, query in enumerate(queries):
        search_results = retrieval.search(
            query=query["text"],
            top_k=max(k_values),
            rerank=True,
            hybrid=False,
            collection_name=collection_name,
        )
        results.append({
            "query_id": query["id"],
            "query_type": query.get("query_type", "unknown"),
            "retrieved": [{"id": r["id"], "score": r.get("score", 0.0)} for r in search_results],
        })
        if (i + 1) % 20 == 0:
            print(f"  [{cell_name}] {i + 1}/{len(queries)}", flush=True)

    # Split by query type
    tech_results = [r for r in results if r["query_type"] == "technical"]
    sem_results = [r for r in results if r["query_type"] == "semantic"]

    tech_metrics = _compute_metrics(tech_results, qrels, k_values)
    sem_metrics = _compute_metrics(sem_results, qrels, k_values)
    all_metrics = _compute_metrics(results, qrels, k_values)

    print(
        f"[{cell_name}] tech_cov@20={tech_metrics.get('coverage@20', 0):.4f} "
        f"sem_cov@20={sem_metrics.get('coverage@20', 0):.4f}",
        flush=True,
    )

    return {
        "cell": cell_name,
        "threshold": threshold,
        "tech_fraction": tech_fraction,
        "n_queries": len(results),
        "n_technical": len(tech_results),
        "n_semantic": len(sem_results),
        "below_min": len(results) < MIN_QUERIES,
        "metrics_all": all_metrics,
        "metrics_technical": tech_metrics,
        "metrics_semantic": sem_metrics,
        "per_query": results,
    }


def _save_checkpoint(data: dict[str, Any], path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.rename(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Experiment 13")
    parser.add_argument("--k-values", nargs="+", type=int, default=[5, 10, 20, 50])
    parser.add_argument("--collection-name", default="documents")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load FreshStack ground truth
    fs_gt_path = SCRIPT_DIR / "ground-truth.json"
    if not fs_gt_path.exists():
        fs_gt_path = SCRIPT_DIR / "freshstack-qrels.json"
    fs_gt = _load_ground_truth(fs_gt_path) if fs_gt_path.exists() else {"queries": [], "qrels": {}}

    # Load Qasper ground truth
    qasper_gt_path = output_dir / "qasper_qrels.json"
    qasper_gt = _load_ground_truth(qasper_gt_path) if qasper_gt_path.exists() else {"queries": [], "qrels": {}}

    # Combine
    technical_queries = [q for q in fs_gt.get("queries", []) if q.get("is_identifier_heavy", False)]
    semantic_queries = qasper_gt.get("queries", [])
    all_qrels = {**fs_gt.get("qrels", {}), **qasper_gt.get("qrels", {})}

    print(f"Technical queries: {len(technical_queries)}", flush=True)
    print(f"Semantic queries: {len(semantic_queries)}", flush=True)

    rng = random.Random(SEED)

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    completed_cells: dict[str, dict[str, Any]] = {}
    if args.resume and checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        completed_cells = checkpoint.get("cells", {})
        print(f"Resuming with {len(completed_cells)} completed cells", flush=True)

    all_cells: list[dict[str, Any]] = []
    for threshold in THRESHOLDS:
        for fraction in FRACTIONS:
            cell_name = f"thr_{threshold}_frac_{fraction}"
            if cell_name in completed_cells:
                all_cells.append(completed_cells[cell_name])
                continue

            sampled = _sample_queries(technical_queries, semantic_queries, fraction, MIN_QUERIES, rng)
            print(f"\nRunning cell: {cell_name} ({len(sampled)} queries)", flush=True)
            cell_result = _run_cell(
                cell_name, threshold, fraction, sampled, all_qrels, args.k_values, args.collection_name,
            )
            all_cells.append(cell_result)
            completed_cells[cell_name] = cell_result
            _save_checkpoint({"cells": completed_cells}, checkpoint_path)

    payload = {
        "experiment": "13-hard-technical-threshold-calibration-2026-06-29",
        "created_at_unix": time.time(),
        "settings": {
            "k_values": args.k_values,
            "thresholds": THRESHOLDS,
            "fractions": FRACTIONS,
            "seed": SEED,
            "min_queries": MIN_QUERIES,
            "embed_model": os.getenv("EMBED_MODEL"),
            "rerank_fetch_multiplier": 3,
            "rerank_max_fetch": 100,
        },
        "cells": all_cells,
    }

    output_path = output_dir / "eval_results.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {output_path}", flush=True)


if __name__ == "__main__":
    main()
