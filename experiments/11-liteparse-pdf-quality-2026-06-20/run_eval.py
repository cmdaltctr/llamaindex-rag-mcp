"""Run Experiment 11 evaluation across the {pypdf, liteparse} × {rerank} cell matrix.

Customised from the canonical eval-runner-pattern.md in the /s-experiment skill.
The "mode" axis here is the PDF parser used to build the ChromaDB index
(which already exists from build_indexes.py), not a runtime mode.

Usage:
    PYTHONUNBUFFERED=1 uv run python -u run_eval.py \\
        --modes pypdf,liteparse \\
        --rerank-cross \\
        --resume \\
        --k-values 5 10 20 50 \\
        2>&1 | tee output/run_eval.log
"""

# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (omrg.ingestion, omrg.retrieval, omrg.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.


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

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")


def _load_ground_truth(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    queries = data.get("queries", [])
    stubs = [q for q in queries if "TODO" in str(q.get("query", ""))]
    if stubs:
        raise SystemExit(
            f"ground_truth.json contains {len(stubs)} TODO stub(s). "
            f"Expand to >=25 real queries before running the experiment."
        )
    if len(queries) < 10:
        raise SystemExit(
            f"Only {len(queries)} queries in {path}; need >=25 for meaningful results."
        )
    return data


def _setup_environment(parser_mode: str, chroma_dir: Path) -> None:
    """Point the retrieval module at the correct pre-built ChromaDB index."""
    os.environ["CHROMA_PERSIST_DIR"] = str(chroma_dir)
    # Hybrid off — isolates the parser variable per protocol.md.
    os.environ["HYBRID_ENABLED"] = "false"

    for mod_name in ("omrg.config", "omrg.retrieval", "omrg.ingestion"):
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        if hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = str(chroma_dir)
        if hasattr(mod, "HYBRID_ENABLED"):
            mod.HYBRID_ENABLED = False

    try:
        from omrg.retrieval import _cached_query_embedding
        _cached_query_embedding.cache_clear()
    except Exception:
        pass


def _parent_id(result: dict) -> str:
    """Extract a bare source filename from a retrieval result dict.

    retrieval.search() returns dicts with a 'source' key holding the
    full file path. We extract the basename to match expected_files
    in ground_truth.json (which uses bare filenames like
    'vaswani2017_attention.pdf').
    """
    source = result.get("source", "")
    return os.path.basename(source) if source else ""


def _metrics_for_query(
    retrieved_ids: list[str],
    query: dict[str, Any],
    k_values: list[int],
) -> dict[str, Any]:
    expected = set(query.get("expected_files", []))
    if not expected:
        return {"hit_at_5": False, "hit_at_10": False, "mrr_at_10": 0.0,
                "coverage_at_20": 0.0}

    hits_by_k: dict[int, bool] = {}
    for k in k_values:
        top_k = retrieved_ids[:k]
        hits_by_k[f"hit_at_{k}"] = any(rid in expected for rid in top_k)

    # MRR@10 — rank of the first relevant result, truncated at 10
    mrr = 0.0
    for rank, rid in enumerate(retrieved_ids[:10], start=1):
        if rid in expected:
            mrr = 1.0 / rank
            break

    # Coverage@20 — fraction of expected files retrieved in top-20
    top_20 = set(retrieved_ids[:20])
    coverage = len(expected & top_20) / len(expected) if expected else 0.0

    # nDCG@10 — graded relevance: 1.0 if file is expected, 0.0 otherwise.
    # DCG with binary relevance and log2 discount.
    dcg = 0.0
    for rank, rid in enumerate(retrieved_ids[:10], start=1):
        if rid in expected:
            dcg += 1.0 / (rank if rank == 1 else rank).bit_length()
    # Ideal DCG = 1.0 (first position) when any expected file exists
    idcg = 1.0 if expected else 0.0
    ndcg = dcg / idcg if idcg > 0 else 0.0

    return {
        **hits_by_k,
        "mrr_at_10": round(mrr, 4),
        "coverage_at_20": round(coverage, 4),
        "ndcg_at_10": round(ndcg, 4),
    }


def _evaluate_cell(
    *,
    parser_mode: str,
    rerank: bool,
    chroma_dir: Path,
    queries: list[dict[str, Any]],
    top_k: int,
    k_values: list[int],
) -> dict[str, Any]:
    import omrg.retrieval as retrieval

    _setup_environment(parser_mode, chroma_dir)
    per_query: list[dict[str, Any]] = []

    for index, query in enumerate(queries, start=1):
        started = time.perf_counter()
        results = retrieval.search(
            query=query["query"],
            top_k=top_k,
            similarity_threshold=0.0,
            rerank=rerank,
            hybrid=False,  # protocol.md: hybrid off to isolate parser variable
            include_diagnostics=True,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        retrieved_ids = [_parent_id(r) for r in results]
        per_query.append({
            "query_index": index,
            "query_id": query.get("query_id", str(index)),
            "category": query.get("category"),
            "expected_files": query.get("expected_files", []),
            "latency_ms": round(latency_ms, 2),
            "metrics": _metrics_for_query(retrieved_ids, query, k_values),
            "top_results": retrieved_ids[:top_k],
        })

        if index % 5 == 0 or index == len(queries):
            print(f"    {parser_mode}/rerank={rerank}: {index}/{len(queries)} "
                  f"queries (last ndcg@10={per_query[-1]['metrics']['ndcg_at_10']:.3f})",
                  flush=True)

    latencies = [row["latency_ms"] for row in per_query]
    p95 = (statistics.quantiles(latencies, n=100, method="inclusive")[94]
           if len(latencies) >= 100 else (max(latencies) if latencies else 0.0))
    return {
        "mode": parser_mode,
        "rerank": rerank,
        "chroma_dir": str(chroma_dir),
        "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p50_latency_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(p95, 2),
        "queries": per_query,
    }


def _cell_key(mode: str, rerank: bool) -> str:
    return f"{mode}__rerank_{str(rerank).lower()}"


def _load_checkpoint(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cells = data.get("cells", [])
        return cells if isinstance(cells, list) else []
    except Exception as exc:
        print(f"Ignoring unreadable checkpoint {path}: {exc}", flush=True)
        return []


def _save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    tmp_path.replace(path)


def _result_payload(
    *,
    ground_truth: dict[str, Any],
    modes: list[str],
    rerank_settings: list[bool],
    k_values: list[int],
    top_k: int,
    cells: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "experiment": "11-liteparse-pdf-quality-2026-06-20",
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "ground_truth_size": len(ground_truth.get("queries", [])),
        "modes": modes,
        "rerank_settings": rerank_settings,
        "k_values": k_values,
        "top_k": top_k,
        "cells": cells,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, default=SCRIPT_DIR)
    parser.add_argument("--modes", default="pypdf,liteparse")
    parser.add_argument("--rerank-cross", action="store_true",
                        help="Run each mode both with and without reranker.")
    parser.add_argument("--k-values", nargs="+", type=int, default=[5, 10, 20, 50])
    parser.add_argument("--limit-queries", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    exp_dir = args.experiment_dir.resolve()
    output_dir = exp_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    gt_path = exp_dir / "ground_truth.json"
    ground_truth = _load_ground_truth(gt_path)
    queries = ground_truth["queries"][: args.limit_queries]

    top_k = max(args.k_values)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    rerank_settings = [False, True] if args.rerank_cross else [True]

    import omrg.retrieval as retrieval
    if "rerank" not in inspect.signature(retrieval.search).parameters:
        raise RuntimeError("retrieval.search does not expose the rerank parameter")

    checkpoint_path = output_dir / "eval_results_checkpoint.json"
    output_path = output_dir / "eval_results.json"
    cells = _load_checkpoint(checkpoint_path) if args.resume and not args.no_resume else []
    completed = {_cell_key(c["mode"], c["rerank"]) for c in cells}

    for mode in modes:
        chroma_dir = output_dir / f"chroma_{mode}"
        if not chroma_dir.exists():
            raise SystemExit(
                f"Missing Chroma index for {mode}: {chroma_dir}. "
                f"Run build_indexes.py --parser {mode} first."
            )
        for rerank in rerank_settings:
            key = _cell_key(mode, rerank)
            if key in completed:
                print(f"Skipping completed cell from checkpoint: {key}", flush=True)
                continue
            print(f"\nEvaluating mode={mode}, rerank={rerank}, top_k={top_k}",
                  flush=True)
            cell = _evaluate_cell(
                parser_mode=mode,
                rerank=rerank,
                chroma_dir=chroma_dir,
                queries=queries,
                top_k=top_k,
                k_values=args.k_values,
            )
            cells.append(cell)
            completed.add(key)
            payload = _result_payload(
                ground_truth=ground_truth,
                modes=modes,
                rerank_settings=rerank_settings,
                k_values=args.k_values,
                top_k=top_k,
                cells=cells,
            )
            _save_checkpoint(checkpoint_path, payload)
            print(f"Checkpoint saved to {checkpoint_path}", flush=True)

    result = _result_payload(
        ground_truth=ground_truth,
        modes=modes,
        rerank_settings=rerank_settings,
        k_values=args.k_values,
        top_k=top_k,
        cells=cells,
    )
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print(f"\nRaw eval results saved to {output_path}", flush=True)


if __name__ == "__main__":
    main()
