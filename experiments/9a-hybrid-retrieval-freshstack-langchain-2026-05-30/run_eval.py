"""Run Experiment 9a dense/hybrid × rerank evaluation through retrieval.search."""

from __future__ import annotations

import argparse
import inspect
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


def _load_ground_truth(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if data.get("corpus", {}).get("total_parent_docs", 0) < 10_000:
        raise SystemExit("Corpus validity failed: fewer than 10,000 parent documents")
    return data


def _setup_environment(mode: str, chroma_dir: Path) -> None:
    if mode == "dense-only":
        os.environ["HYBRID_ENABLED"] = "false"
        os.environ["HYBRID_SPARSE_BACKEND"] = "bm25"
    elif mode == "hybrid_bm25":
        os.environ["HYBRID_ENABLED"] = "true"
        os.environ["HYBRID_SPARSE_BACKEND"] = "bm25"
    else:
        raise ValueError(f"unknown mode: {mode}")
    os.environ["HYBRID_RRF_K"] = os.getenv("HYBRID_RRF_K", "60")
    os.environ["CHROMA_PERSIST_DIR"] = str(chroma_dir)

    for mod_name in ("rag_mcp.config", "rag_mcp.retrieval", "rag_mcp.ingestion"):
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        if hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = str(chroma_dir)
        if hasattr(mod, "HYBRID_ENABLED"):
            mod.HYBRID_ENABLED = mode != "dense-only"
        if hasattr(mod, "HYBRID_SPARSE_BACKEND"):
            mod.HYBRID_SPARSE_BACKEND = "bm25"
        if hasattr(mod, "RESOLVED_HYBRID_SPARSE_BACKEND"):
            mod.RESOLVED_HYBRID_SPARSE_BACKEND = "bm25"

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


def _parent_id(result: dict[str, Any]) -> str:
    meta = result.get("metadata") or {}
    return str(meta.get("freshstack_id") or result.get("id") or result.get("source") or "")


def _rank_map(parent_ids: list[str]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for rank, parent_id in enumerate(parent_ids, start=1):
        ranks.setdefault(parent_id, rank)
    return ranks


def _alpha_ndcg(parent_ids: list[str], nuggets: list[dict[str, Any]], k: int = 10, alpha: float = 0.5) -> float:
    nugget_rels = [set(n.get("relevant_corpus_ids") or []) for n in nuggets]
    if not nugget_rels:
        return 0.0

    def dcg(ranking: list[str]) -> float:
        seen = [0 for _ in nugget_rels]
        total = 0.0
        import math

        for rank, doc_id in enumerate(ranking[:k], start=1):
            gain = 0.0
            for idx, rels in enumerate(nugget_rels):
                if doc_id in rels:
                    gain += (1.0 - alpha) ** seen[idx]
                    seen[idx] += 1
            if gain:
                total += gain / math.log2(rank + 1)
        return total

    observed = dcg(parent_ids)
    candidate_docs = sorted(set().union(*nugget_rels))
    ideal: list[str] = []
    remaining = candidate_docs[:]
    while remaining and len(ideal) < k:
        best_doc = max(remaining, key=lambda doc: dcg(ideal + [doc]))
        ideal.append(best_doc)
        remaining.remove(best_doc)
    ideal_score = dcg(ideal)
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


def _prewarm_sparse_index() -> float | None:
    try:
        import chromadb
        from rag_mcp.config import CHROMA_PERSIST_DIR
        from rag_mcp.sparse_retriever import BM25SparseRetriever

        db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        collection = db.get_collection("documents")
        started = time.perf_counter()
        BM25SparseRetriever("documents").query("langchain", 1)
        return round((time.perf_counter() - started) * 1000, 2)
    except Exception:
        return None


def _evaluate_cell(
    *,
    mode: str,
    rerank: bool,
    chroma_dir: Path,
    queries: list[dict[str, Any]],
    top_k: int,
    warmup_queries: int,
) -> dict[str, Any]:
    import rag_mcp.retrieval as retrieval

    _setup_environment(mode, chroma_dir)
    bm25_build_ms = _prewarm_sparse_index() if mode == "hybrid_bm25" else None

    for query in queries[:warmup_queries]:
        retrieval.search(
            query=query["query"],
            top_k=min(10, top_k),
            similarity_threshold=0.0,
            rerank=rerank,
            hybrid=mode != "dense-only",
            include_diagnostics=True,
        )

    per_query: list[dict[str, Any]] = []
    for index, query in enumerate(queries, start=1):
        started = time.perf_counter()
        results = retrieval.search(
            query=query["query"],
            top_k=top_k,
            similarity_threshold=0.0,
            rerank=rerank,
            hybrid=mode != "dense-only",
            include_diagnostics=True,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        parent_ids = [_parent_id(result) for result in results]
        metrics = _metrics_for_query(parent_ids, query)
        top_results = []
        for rank, result in enumerate(results[:top_k], start=1):
            top_results.append({
                "rank": rank,
                "parent_id": _parent_id(result),
                "score": result.get("score"),
                "dense_rank": result.get("dense_rank"),
                "sparse_rank": result.get("sparse_rank"),
                "fused_rank": result.get("fused_rank"),
                "source": result.get("source"),
            })
        per_query.append({
            "query_index": index,
            "query_id": query["query_id"],
            "category": query.get("category"),
            "source_kind": query.get("source_kind"),
            "named_case": query.get("named_case") or (query.get("metadata") or {}).get("named_case"),
            "latency_ms": round(latency_ms, 2),
            "metrics": metrics,
            "top_results": top_results,
        })
        if index % 25 == 0 or index == len(queries):
            print(f"    {mode}/rerank={rerank}: {index}/{len(queries)} queries", flush=True)

    latencies = [row["latency_ms"] for row in per_query]
    p95 = statistics.quantiles(latencies, n=100, method="inclusive")[94] if latencies else 0.0
    return {
        "mode": mode,
        "rerank": rerank,
        "chroma_dir": str(chroma_dir),
        "bm25_build_ms": bm25_build_ms,
        "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p50_latency_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(p95, 2),
        "queries": per_query,
    }


def _result_payload(
    *,
    ground_truth: dict[str, Any],
    modes: list[str],
    rerank_settings: list[bool],
    k_values: list[int],
    top_k: int,
    cells: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the persisted result/checkpoint payload."""

# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (rag_mcp.ingestion, rag_mcp.retrieval, rag_mcp.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.

    return {
        "experiment": ground_truth.get("experiment"),
        "created_at_unix": time.time(),
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "settings": {
            "modes": modes,
            "rerank_settings": rerank_settings,
            "k_values": k_values,
            "top_k_requested": top_k,
            "hybrid_rrf_k": int(os.getenv("HYBRID_RRF_K", "60")),
            "rerank_max_fetch": int(os.getenv("RERANK_MAX_FETCH", "50")),
            "rerank_fetch_multiplier": int(os.getenv("RERANK_FETCH_MULTIPLIER", "10")),
            "embed_model": os.getenv("EMBED_MODEL"),
        },
        "corpus": ground_truth.get("corpus"),
        "identifier_classifier": ground_truth.get("identifier_classifier"),
        "cells": cells,
    }


def _cell_key(mode: str, rerank: bool) -> str:
    return f"{mode}__rerank_{str(rerank).lower()}"


def _load_checkpoint(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        cells = data.get("cells", [])
        if isinstance(cells, list):
            return cells
    except Exception as exc:
        print(f"Ignoring unreadable checkpoint {path}: {exc}", flush=True)
    return []


def _save_checkpoint(
    path: Path,
    *,
    ground_truth: dict[str, Any],
    modes: list[str],
    rerank_settings: list[bool],
    k_values: list[int],
    top_k: int,
    cells: list[dict[str, Any]],
) -> None:
    payload = _result_payload(
        ground_truth=ground_truth,
        modes=modes,
        rerank_settings=rerank_settings,
        k_values=k_values,
        top_k=top_k,
        cells=cells,
    )
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, default=SCRIPT_DIR)
    parser.add_argument("--modes", default="dense-only,hybrid_bm25")
    parser.add_argument("--rerank-cross", action="store_true")
    parser.add_argument("--k-values", nargs="+", type=int, default=[5, 10, 20, 50])
    parser.add_argument("--warmup-queries", type=int, default=int(os.getenv("EXP9A_WARMUP_QUERIES", "3")))
    parser.add_argument("--limit-queries", type=int, default=None)
    parser.add_argument("--resume", action="store_true", help="Load eval_results_checkpoint.json and skip completed cells")
    parser.add_argument("--no-resume", action="store_true", help="Ignore any checkpoint even if it exists")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    exp_dir = args.experiment_dir.resolve()
    output_dir = exp_dir / "output"
    gt_path = output_dir / "ground-truth.json"
    if not gt_path.exists():
        gt_path = exp_dir / "ground-truth.json"
    ground_truth = _load_ground_truth(gt_path)
    queries = ground_truth["queries"][: args.limit_queries]
    top_k = max(args.k_values)
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    rerank_settings = [False, True] if args.rerank_cross else [True]

    import rag_mcp.retrieval as retrieval
    if "hybrid" not in inspect.signature(retrieval.search).parameters:
        raise RuntimeError("retrieval.search does not expose the hybrid parameter")

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    output_path = output_dir / "eval_results.json"
    cells: list[dict[str, Any]] = []
    if args.resume and not args.no_resume:
        cells = _load_checkpoint(checkpoint_path)
        if cells:
            loaded = ", ".join(_cell_key(c["mode"], c["rerank"]) for c in cells)
            print(f"Loaded checkpoint with completed cells: {loaded}", flush=True)
    completed = {_cell_key(c["mode"], c["rerank"]) for c in cells}

    for mode in modes:
        chroma_dir = output_dir / ("chroma_dense" if mode == "dense-only" else "chroma_hybrid_bm25")
        if not chroma_dir.exists():
            raise SystemExit(f"Missing Chroma index for {mode}: {chroma_dir}")
        for rerank in rerank_settings:
            key = _cell_key(mode, rerank)
            if key in completed:
                print(f"Skipping completed cell from checkpoint: {key}", flush=True)
                continue
            print(f"Evaluating mode={mode}, rerank={rerank}, top_k={top_k}")
            cells.append(_evaluate_cell(
                mode=mode,
                rerank=rerank,
                chroma_dir=chroma_dir,
                queries=queries,
                top_k=top_k,
                warmup_queries=args.warmup_queries,
            ))
            completed.add(key)
            _save_checkpoint(
                checkpoint_path,
                ground_truth=ground_truth,
                modes=modes,
                rerank_settings=rerank_settings,
                k_values=args.k_values,
                top_k=top_k,
                cells=cells,
            )
            print(f"Checkpoint saved to {checkpoint_path}", flush=True)

    result = _result_payload(
        ground_truth=ground_truth,
        modes=modes,
        rerank_settings=rerank_settings,
        k_values=args.k_values,
        top_k=top_k,
        cells=cells,
    )
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Raw eval results saved to {output_path}")


if __name__ == "__main__":
    main()
