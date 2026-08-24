"""Run Experiment 14: LiteParse promotion on Qasper corpus.

6-cell grid (protocol v2.1): {pypdf, liteparse, pdf_inspector} ×
{rerank-off, rerank-on}.
Validates H1 (corpus validity), H2 (speed), H3 (reranker benefit).

Migrated to the v2 surface (add-chroma-cloud-backend): retrieval goes
through ``rag_mcp.core.retrieval.search`` with an injected store from
``experiments/_lib/storage.py`` — no environment mutation or
module-constant patching.  Works in local and cloud Chroma modes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def build_eval_cell_matrix() -> list[dict[str, Any]]:
    """Return the six evaluation cells as plan-comparable dicts (D15).

    Shape matches ``plan.json`` cells: ``{"id": ..., "factors": {...}}``.
    ``plan.json`` is the machine truth for the cell matrix; the agreement
    tests in ``tests/test_experiment_14_harness.py`` compare this pure
    generator against the plan via ``ExperimentPlan.assert_runner_cells``.
    Protocol v2.1 (2026-08-23): pdf_inspector joins as the third reader.
    """
    return [
        {"id": "pypdf_off", "factors": {"reader": "pypdf", "rerank": False}},
        {"id": "pypdf_on", "factors": {"reader": "pypdf", "rerank": True}},
        {"id": "liteparse_off", "factors": {"reader": "liteparse", "rerank": False}},
        {"id": "liteparse_on", "factors": {"reader": "liteparse", "rerank": True}},
        {"id": "pdf_inspector_off", "factors": {"reader": "pdf_inspector", "rerank": False}},
        {"id": "pdf_inspector_on", "factors": {"reader": "pdf_inspector", "rerank": True}},
    ]


# Execution view derived from the pure generator above — same six cells,
# same order and values.
CELLS = [
    {"name": cell["id"], "reader": cell["factors"]["reader"], "rerank": cell["factors"]["rerank"]}
    for cell in build_eval_cell_matrix()
]


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
    latencies: list[float] = []
    for result in results:
        latencies.append(result.get("latency_ms", 0.0))
    latencies.sort()
    if latencies:
        p95_idx = int(len(latencies) * 0.95)
        metrics["p95_ms"] = latencies[min(p95_idx, len(latencies) - 1)]

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


def _resolve_cell_runtime(reader: str, rerank: bool) -> tuple[Any, str]:
    """Build the per-reader store/collection from the shared helper.

    The reader is part of the immutable index identity (parsed text
    differs), so each reader cell resolves its own collection.
    """
    from experiments._lib.storage import experiment_storage_config, identity_embed_model

    model = os.getenv("EMBED_MODEL")
    if not model:
        raise SystemExit("EMBED_MODEL is required; set it in .env or the environment")
    chroma_dir = str(SCRIPT_DIR / "output" / f"chroma_{reader}")
    storage = experiment_storage_config(
        experiment_id="exp14",
        corpus="qasper",
        provider="ollama",
        model=model,
        parser=reader,
        persist_dir=chroma_dir,
    )
    store = storage.build_store()

    from llama_index.core import Settings as LlamaIndexSettings

    from rag_mcp.core.vectordb import set_default_store

    # Pin the query embedder to the index identity; ambient Settings()
    # could select a different provider and query with incompatible vectors.
    LlamaIndexSettings.embed_model = identity_embed_model(model)
    set_default_store(store)
    return store, storage.collection_name


def _run_cell(
    cell: dict[str, Any],
    queries: list[dict[str, Any]],
    qrels: dict[str, dict[str, int]],
    k_values: list[int],
) -> dict[str, Any]:
    from rag_mcp.core.retrieval import search

    reader = cell["reader"]
    rerank = cell["rerank"]

    store, collection_name = _resolve_cell_runtime(reader, rerank)

    results: list[dict[str, Any]] = []
    for i, query in enumerate(queries):
        t0 = time.perf_counter()
        search_results = search(
            query=query["text"],
            top_k=max(k_values),
            rerank=rerank,
            hybrid=False,
            collection_name=collection_name,
            store=store,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        results.append(
            {
                "query_id": query["id"],
                "retrieved": [
                    {"id": r["id"], "score": r.get("score", 0.0)} for r in search_results
                ],
                "latency_ms": latency_ms,
            }
        )
        if (i + 1) % 20 == 0:
            print(f"  [{cell['name']}] {i + 1}/{len(queries)}", flush=True)

    metrics = _compute_metrics(results, qrels, k_values)
    print(
        f"[{cell['name']}] cov@20={metrics.get('coverage@20', 0):.4f} "
        f"hit@5={metrics.get('hit@5', 0):.4f} p95={metrics.get('p95_ms', 0):.0f}ms",
        flush=True,
    )

    return {
        "cell": cell["name"],
        "reader": reader,
        "rerank": rerank,
        "n_queries": len(results),
        "metrics": metrics,
        "per_query": results,
    }


def _save_checkpoint(data: dict[str, Any], path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.rename(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Experiment 14")
    parser.add_argument("--k-values", nargs="+", type=int, default=[5, 10, 20, 50])
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # The frozen qrels live at the experiment root (written there by
    # prepare_qasper_pdfs.py and gitignored); output/ holds only artefacts.
    gt_path = SCRIPT_DIR / "qasper_qrels.json"
    gt = _load_ground_truth(gt_path)
    queries = gt.get("queries", [])
    qrels = gt.get("qrels", {})

    print(f"Queries: {len(queries)}", flush=True)

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    completed_cells: dict[str, dict[str, Any]] = {}
    if args.resume and checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        completed_cells = checkpoint.get("cells", {})
        print(f"Resuming with {len(completed_cells)} completed cells", flush=True)

    all_cells: list[dict[str, Any]] = []
    for cell in CELLS:
        if cell["name"] in completed_cells:
            all_cells.append(completed_cells[cell["name"]])
            continue

        print(f"\nRunning cell: {cell['name']}", flush=True)
        cell_result = _run_cell(cell, queries, qrels, args.k_values)
        all_cells.append(cell_result)
        completed_cells[cell["name"]] = cell_result
        _save_checkpoint({"cells": completed_cells}, checkpoint_path)

    # Load ingestion times from index build metadata
    ingestion_times: dict[str, float] = {}
    # Protocol v2.1: three readers — pdf_inspector timing is H2 evidence too.
    for reader in ["pypdf", "liteparse", "pdf_inspector"]:
        build_info_path = output_dir / f"index_build_{reader}.json"
        if build_info_path.exists():
            build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
            ingestion_times[reader] = build_info.get("ingestion_time_s", 0.0)

    payload = {
        "experiment": "14-liteparse-qasper-promotion-2026-06-29",
        "created_at_unix": time.time(),
        "settings": {
            "k_values": args.k_values,
            "embed_model": os.getenv("EMBED_MODEL"),
            "rerank_fetch_multiplier": 3,
            "rerank_max_fetch": 100,
            "ingestion_times": ingestion_times,
        },
        "cells": all_cells,
    }

    output_path = output_dir / "eval_results.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {output_path}", flush=True)


if __name__ == "__main__":
    main()
