"""Run Experiment 15: gte-reranker-modernbert-base A/B Comparison.

3-cell grid on FreshStack LangChain (hybrid_bm25):
  1. rerank-off baseline
  2. MiniLM reranker (cross-encoder/ms-marco-MiniLM-L-6-v2)
  3. gte-reranker (Alibaba-NLP/gte-reranker-modernbert-base)

Reuses Exp 12's ChromaDB hybrid index and ground truth.
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
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ── Models ────────────────────────────────────────────────────────────────

MINILM_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
GTE_MODEL = "Alibaba-NLP/gte-reranker-modernbert-base"


# ── Ground truth ──────────────────────────────────────────────────────────


def _load_ground_truth(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("queries"):
        raise SystemExit(f"No queries in {path}")
    return data


# ── Environment / reranker switching ──────────────────────────────────────


def _patch_module_attrs(mod: Any, chroma_dir: Path) -> None:
    """Patch module-level globals for the current cell."""
    if hasattr(mod, "CHROMA_PERSIST_DIR"):
        mod.CHROMA_PERSIST_DIR = str(chroma_dir)
    if hasattr(mod, "HYBRID_ENABLED"):
        mod.HYBRID_ENABLED = True
    if hasattr(mod, "HYBRID_SPARSE_BACKEND"):
        mod.HYBRID_SPARSE_BACKEND = "bm25"
    if hasattr(mod, "RESOLVED_HYBRID_SPARSE_BACKEND"):
        mod.RESOLVED_HYBRID_SPARSE_BACKEND = "bm25"
    if hasattr(mod, "RERANK_FETCH_MULTIPLIER"):
        mod.RERANK_FETCH_MULTIPLIER = 3
    if hasattr(mod, "RERANK_MAX_FETCH"):
        mod.RERANK_MAX_FETCH = 100


def _clear_caches() -> None:
    """Clear all retrieval caches between cells."""
    try:
        from rag_mcp.retrieval import _cached_query_embedding

        _cached_query_embedding.cache_clear()
    except Exception:
        pass
    try:
        from rag_mcp.sparse_retriever import BM25SparseRetriever

        BM25SparseRetriever.clear_all_caches()
    except Exception:
        pass


def _setup_reranker_model(model_name: str | None) -> None:
    """Switch the reranker to the specified model.

    Resets the CrossEncoderReranker singleton so the new model loads
    fresh on the next rerank() call.  For rerank-off cells, pass None.
    """
    from rag_mcp import reranker as reranker_mod

    # Reset the singleton — the new model will load on next use.
    reranker_mod.CrossEncoderReranker._instance = None

    if model_name:
        reranker_mod.RERANK_MODEL = model_name
        os.environ["RERANK_MODEL"] = model_name
        print(f"  Reranker model set to: {model_name}", flush=True)
    else:
        print("  Reranker disabled (rerank=False)", flush=True)


def _setup_environment(chroma_dir: Path) -> None:
    """Set up the environment for a hybrid_bm25 cell."""
    os.environ["HYBRID_ENABLED"] = "true"
    os.environ["HYBRID_SPARSE_BACKEND"] = "bm25"
    os.environ["CHROMA_PERSIST_DIR"] = str(chroma_dir)

    for mod_name in ("rag_mcp.config", "rag_mcp.retrieval", "rag_mcp.ingestion"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            _patch_module_attrs(mod, chroma_dir)

    _clear_caches()


# ── Metrics ───────────────────────────────────────────────────────────────


def _parent_id(result: dict[str, Any]) -> str:
    meta = result.get("metadata") or {}
    return str(
        meta.get("freshstack_id") or result.get("id") or result.get("source") or ""
    )


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
        best_doc = max(
            remaining, key=lambda doc: _dcg(ideal + [doc], nugget_rels, k, alpha)
        )
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
        "recall_at_50": len(relevant & set(parent_ids[:50])) / len(relevant)
        if relevant
        else 0.0,
        "alpha_ndcg_at_10": _alpha_ndcg(parent_ids, nuggets, k=10),
        "hit_at_1": first_rank is not None and first_rank <= 1,
        "hit_at_5": first_rank is not None and first_rank <= 5,
        "hit_at_10": first_rank is not None and first_rank <= 10,
        "mrr_at_10": (1.0 / first_rank)
        if first_rank is not None and first_rank <= 10
        else 0.0,
    }


# ── Cell evaluation ───────────────────────────────────────────────────────


def _evaluate_cell(
    cell_id: str,
    reranker_model: str | None,
    rerank: bool,
    chroma_dir: Path,
    queries: list[dict[str, Any]],
    top_k: int,
    warmup_queries: int,
) -> dict[str, Any]:
    import rag_mcp.retrieval as retrieval

    _setup_environment(chroma_dir)
    _setup_reranker_model(reranker_model)

    # Warmup — primes the reranker model download/load and the embedding cache.
    if rerank:
        for query in queries[:warmup_queries]:
            retrieval.search(
                query=query["query"][:4000],
                top_k=min(10, top_k),
                similarity_threshold=0.0,
                rerank=True,
                hybrid=True,
                include_diagnostics=True,
            )
        print(f"  Warmup complete ({warmup_queries} queries)", flush=True)

    _clear_caches()

    per_query: list[dict[str, Any]] = []
    for index, query in enumerate(queries, start=1):
        started = time.perf_counter()
        results = retrieval.search(
            query=query["query"][:4000],
            top_k=top_k,
            similarity_threshold=0.0,
            rerank=rerank,
            hybrid=True,
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
            print(
                f"    {cell_id}: {index}/{len(queries)} queries", flush=True
            )

    latencies = [row["latency_ms"] for row in per_query]
    p95 = (
        statistics.quantiles(latencies, n=100, method="inclusive")[94]
        if latencies
        else 0.0
    )

    n = len(per_query)
    agg: dict[str, float] = {}
    for key in ("coverage_at_20", "recall_at_50", "alpha_ndcg_at_10", "mrr_at_10"):
        vals = [pq["metrics"][key] for pq in per_query]
        agg[key] = sum(vals) / n if n else 0.0
    for key in ("hit_at_1", "hit_at_5", "hit_at_10"):
        vals = [pq["metrics"][key] for pq in per_query]
        agg[key] = sum(1 for v in vals if v) / n if n else 0.0

    return {
        "cell_id": cell_id,
        "reranker_model": reranker_model,
        "rerank": rerank,
        "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p50_latency_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(p95, 2),
        "aggregate_metrics": agg,
        "queries": per_query,
    }


# ── Checkpoint / resume ───────────────────────────────────────────────────


def _save_checkpoint(path: Path, cells: list[dict[str, Any]]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"cells": cells}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(path)


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Experiment 15")
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
    print(f"Loaded {len(queries)} queries, top_k={top_k}", flush=True)

    chroma_dir = output_dir / "chroma_hybrid_bm25"
    if not chroma_dir.exists():
        raise SystemExit(
            f"Missing Chroma index: {chroma_dir}. "
            "Symlink from Exp 12: "
            "ln -s ../../12-hybrid-default-promotion-2026-06-29/output/chroma_hybrid_bm25 "
            "output/chroma_hybrid_bm25"
        )

    # 3-cell grid: all hybrid_bm25, varying reranker model.
    cells_config = [
        ("hybrid_off", None, False),
        ("hybrid_minilm", MINILM_MODEL, True),
        ("hybrid_gte", GTE_MODEL, True),
    ]

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    completed_cells: list[dict[str, Any]] = []
    completed_keys: set[str] = set()
    if args.resume and checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        completed_cells = checkpoint.get("cells", [])
        completed_keys = {c["cell_id"] for c in completed_cells}
        print(f"Resuming with {len(completed_keys)} completed cells", flush=True)

    for cell_id, reranker_model, rerank in cells_config:
        if cell_id in completed_keys:
            print(f"Skipping completed cell: {cell_id}", flush=True)
            continue

        print(f"\n{'='*60}", flush=True)
        print(f"Evaluating cell: {cell_id}", flush=True)
        print(f"  rerank={rerank}, model={reranker_model or 'N/A'}", flush=True)
        print(f"{'='*60}", flush=True)

        cell_result = _evaluate_cell(
            cell_id=cell_id,
            reranker_model=reranker_model,
            rerank=rerank,
            chroma_dir=chroma_dir,
            queries=queries,
            top_k=top_k,
            warmup_queries=args.warmup_queries,
        )
        completed_cells.append(cell_result)
        _save_checkpoint(checkpoint_path, completed_cells)
        print(f"  Cell complete. Checkpoint saved.", flush=True)
        print(
            f"  Coverage@20={cell_result['aggregate_metrics']['coverage_at_20']:.4f}, "
            f"Hit@1={cell_result['aggregate_metrics']['hit_at_1']:.4f}, "
            f"P95={cell_result['p95_latency_ms']:.0f}ms",
            flush=True,
        )

    payload = {
        "experiment": "15-gte-reranker-swap-2026-07-31",
        "created_at_unix": time.time(),
        "hardware": {"platform": platform.platform()},
        "settings": {
            "k_values": args.k_values,
            "top_k_requested": top_k,
            "rerank_fetch_multiplier": 3,
            "rerank_max_fetch": 100,
            "embed_model": os.getenv("EMBED_MODEL"),
            "corpus": "FreshStack LangChain (reused from Exp 12)",
            "n_queries": len(queries),
        },
        "cells": completed_cells,
    }

    output_path = output_dir / "eval_results.json"
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nResults saved to {output_path}", flush=True)


if __name__ == "__main__":
    main()
