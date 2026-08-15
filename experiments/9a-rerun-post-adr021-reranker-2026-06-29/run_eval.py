"""Run Experiment 9a-rerun: Post-ADR-021 Reranker Validation.

Same 4-cell grid as Exp 9a but with post-ADR-021 config
(MULTIPLIER=3, MAX_FETCH=100), giving fetch_k=150 at top_k=50.
Reuses Exp 9a's ChromaDB indexes and ground truth.

Migrated to the v2 surface (add-chroma-cloud-backend): retrieval goes
through ``rag_mcp.core.retrieval.search`` with an explicitly injected
store obtained from ``experiments/_lib/storage.py`` — no environment
mutation or module-constant patching.  Works in local and cloud Chroma
modes; retrieval-only cells reuse the immutable index read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _load_ground_truth(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if data.get("corpus", {}).get("total_parent_docs", 0) < 10_000:
        raise SystemExit("Corpus validity failed: fewer than 10,000 parent documents")
    return data


def _resolve_cell_runtime(mode: str, chroma_dir: Path) -> tuple[Any, str]:
    """Build the cell store/collection from the shared helper and clear caches.

    Retrieval knobs (hybrid on/off, sparse backend, fetch pool) are
    passed per ``search`` call instead of patched into module globals.
    """
    from experiments._lib.storage import experiment_storage_config

    model = os.getenv("EMBED_MODEL", "unknown")
    storage = experiment_storage_config(
        experiment_id="exp9a",
        corpus="freshstack",
        provider="ollama",
        model=model,
        persist_dir=str(chroma_dir),
    )
    store = storage.build_store()

    from llama_index.core import Settings as LlamaIndexSettings

    from rag_mcp.compose import build_embed_model
    from rag_mcp.config import Settings
    from rag_mcp.core.vectordb import set_default_store

    LlamaIndexSettings.embed_model = build_embed_model(Settings())
    set_default_store(store)

    try:
        from rag_mcp.core.retrieval.dense import _cached_query_embedding

        _cached_query_embedding.cache_clear()
    except Exception:
        pass
    try:
        from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

        BM25SparseRetriever._cache.clear()
    except Exception:
        pass
    return store, storage.collection_name


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
        "first_relevant_rank": first_rank,
    }


def _evaluate_cell(
    mode: str,
    rerank: bool,
    chroma_dir: Path,
    queries: list[dict[str, Any]],
    top_k: int,
    warmup_queries: int,
) -> dict[str, Any]:
    from rag_mcp.core.retrieval import search

    store, collection_name = _resolve_cell_runtime(mode, chroma_dir)

    for query in queries[:warmup_queries]:
        search(
            query=query["query"][:4000],
            top_k=min(10, top_k),
            similarity_threshold=0.0,
            rerank=rerank,
            hybrid=mode != "dense-only",
            collection_name=collection_name,
            store=store,
            include_diagnostics=True,
        )

    per_query: list[dict[str, Any]] = []
    for index, query in enumerate(queries, start=1):
        started = time.perf_counter()
        results = search(
            query=query["query"][:4000],
            top_k=top_k,
            similarity_threshold=0.0,
            rerank=rerank,
            hybrid=mode != "dense-only",
            collection_name=collection_name,
            store=store,
            include_diagnostics=True,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        parent_ids = [_parent_id(result) for result in results]
        metrics = _metrics_for_query(parent_ids, query)
        per_query.append(
            {
                "query_index": index,
                "query_id": query["query_id"],
                "category": query.get("category"),
                "latency_ms": round(latency_ms, 2),
                "metrics": metrics,
            }
        )
        if index % 25 == 0 or index == len(queries):
            print(f"    {mode}/rerank={rerank}: {index}/{len(queries)} queries", flush=True)

    latencies = [row["latency_ms"] for row in per_query]
    p95 = statistics.quantiles(latencies, n=100, method="inclusive")[94] if latencies else 0.0

    n = len(per_query)
    agg: dict[str, float] = {}
    for key in ("coverage_at_20", "recall_at_50", "alpha_ndcg_at_10", "mrr_at_10"):
        vals = [pq["metrics"][key] for pq in per_query]
        agg[key] = sum(vals) / n if n else 0.0
    for key in ("hit_at_5", "hit_at_10"):
        vals = [pq["metrics"][key] for pq in per_query]
        agg[key] = sum(1 for v in vals if v) / n if n else 0.0

    return {
        "mode": mode,
        "rerank": rerank,
        "chroma_dir": str(chroma_dir),
        "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p50_latency_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(p95, 2),
        "aggregate_metrics": agg,
        "queries": per_query,
    }


def _cell_key(mode: str, rerank: bool) -> str:
    return f"{mode}__rerank_{str(rerank).lower()}"


def _save_checkpoint(path: Path, cells: list[dict[str, Any]]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"cells": cells}, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Experiment 9a-rerun")
    parser.add_argument("--k-values", nargs="+", type=int, default=[5, 10, 20, 50])
    parser.add_argument("--warmup-queries", type=int, default=3)
    parser.add_argument("--limit-queries", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    gt_path = SCRIPT_DIR / "ground-truth.json"
    ground_truth = _load_ground_truth(gt_path)
    queries = ground_truth["queries"][: args.limit_queries]
    top_k = max(args.k_values)
    print(f"Loaded {len(queries)} queries", flush=True)

    cells_config = [
        ("dense-only", False),
        ("dense-only", True),
        ("hybrid_bm25", False),
        ("hybrid_bm25", True),
    ]

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    completed_cells: list[dict[str, Any]] = []
    completed_keys: set[str] = set()
    if args.resume and checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        completed_cells = checkpoint.get("cells", [])
        completed_keys = {_cell_key(c["mode"], c["rerank"]) for c in completed_cells}
        print(f"Resuming with {len(completed_keys)} completed cells", flush=True)

    for mode, rerank in cells_config:
        key = _cell_key(mode, rerank)
        if key in completed_keys:
            print(f"Skipping completed cell: {key}", flush=True)
            continue

        chroma_dir = output_dir / ("chroma_dense" if mode == "dense-only" else "chroma_hybrid_bm25")
        if not chroma_dir.exists():
            raise SystemExit(f"Missing Chroma index: {chroma_dir}")

        print(f"\nEvaluating mode={mode}, rerank={rerank}, top_k={top_k}", flush=True)
        cell_result = _evaluate_cell(mode, rerank, chroma_dir, queries, top_k, args.warmup_queries)
        completed_cells.append(cell_result)
        _save_checkpoint(checkpoint_path, completed_cells)

    payload = {
        "experiment": "9a-rerun-post-adr021-reranker-2026-06-29",
        "created_at_unix": time.time(),
        "hardware": {"platform": platform.platform(), "machine": platform.machine()},
        "settings": {
            "k_values": args.k_values,
            "top_k_requested": top_k,
            "rerank_fetch_multiplier": 3,
            "rerank_max_fetch": 100,
            "effective_fetch_k": 150,
            "embed_model": os.getenv("EMBED_MODEL"),
        },
        "corpus": ground_truth.get("corpus"),
        "cells": completed_cells,
    }

    output_path = output_dir / "eval_results.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {output_path}", flush=True)


if __name__ == "__main__":
    main()
