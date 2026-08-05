"""Hybrid retrieval quality experiment.

Runs a cell grid: retrieval mode × reranker on/off.

  - dense-only / rerank-off: pure vector baseline
  - dense-only / rerank-on:  current production (Tier 2 pool defaults)
  - hybrid_bm25 / rerank-off: pure RRF effect
  - hybrid_bm25 / rerank-on:  full hybrid + reranker (production candidate)
  - hybrid_native / rerank-on (optional): only if pinned ChromaDB supports it

Reports:

  - Hit@1 / Hit@5 / MRR@10 / Recall@10 per query category
    (rare-term / semantic / mixed)
  - Named regression case: the Colosseum query MUST hit top-1 under hybrid
  - Fusion source ranks (dense_rank, sparse_rank, fused_rank) per query
  - End-to-end latency mean / P95

Run with:
    cd experiments/9-hybrid-retrieval-2026-05-27
    uv run python run_eval.py --modes dense-only,hybrid_bm25 --rerank-cross

The cell grid is hard to enumerate from one set of CLI flags, so the runner
expands `--modes` × `[off, on]` automatically when `--rerank-cross` is set.
"""

# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (rag_mcp.ingestion, rag_mcp.retrieval, rag_mcp.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.


from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Ensure project source is importable.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent
CORPUS_DIR = EXPERIMENT_DIR / "corpus"
GROUND_TRUTH_PATH = EXPERIMENT_DIR / "ground-truth.json"

# Reranker pool defaults — should be set per Exp 5 outcome.
DEFAULT_RERANK_MAX_FETCH = int(os.getenv("RERANK_MAX_FETCH", "50"))
DEFAULT_RERANK_FETCH_MULTIPLIER = int(os.getenv("RERANK_FETCH_MULTIPLIER", "10"))

# RRF fusion constant.
DEFAULT_RRF_K = int(os.getenv("HYBRID_RRF_K", "60"))

# Warmup discarded. Override for local reruns while tuning the corpus.
WARMUP_QUERIES = int(os.getenv("EXP9_WARMUP_QUERIES", "50"))


@dataclass
class QueryResult:
    """Per-query result."""

    query: str
    expected_source: str
    expected_answer: str | None
    category: str
    named_case: str | None
    top_k_sources: list[str] = field(default_factory=list)
    top_k_scores: list[float] = field(default_factory=list)
    fusion_ranks: dict = field(default_factory=dict)  # {dense_rank, sparse_rank, fused_rank}
    hit_rank: int | None = None
    hit_at_1: bool = False
    hit_at_5: bool = False
    recall_at_10: bool = False
    answer_hit: bool = False
    latency_ms: float = 0.0


@dataclass
class CellResult:
    """One cell of the (mode × reranker) grid."""

    mode: str
    rerank: bool
    queries: list[QueryResult] = field(default_factory=list)
    metrics_by_category: dict[str, dict[str, float]] = field(default_factory=dict)
    named_cases: dict[str, dict] = field(default_factory=dict)
    mean_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0


def _load_ground_truth() -> list[dict]:
    if not GROUND_TRUTH_PATH.exists():
        print(f"  ERROR: ground-truth not found: {GROUND_TRUTH_PATH}")
        print("  Pre-write 18-25 queries with category, expected_source, "
              "expected_answer, optional named_case (see protocol.md Step 2)")
        sys.exit(1)
    with open(GROUND_TRUTH_PATH) as f:
        data = json.load(f)
    queries = data.get("queries", [])
    if not queries:
        print("  ERROR: no queries in ground-truth.json")
        sys.exit(1)
    return queries


def _validate_corpus() -> None:
    """Confirm the three corpus packs exist."""
    required = ["exp1-fixtures", "rare-term-pack", "semantic-pack"]
    missing = [p for p in required if not (CORPUS_DIR / p).exists()]
    if missing:
        print(f"  ERROR: missing corpus packs: {missing}")
        print("  See protocol.md Step 1 to build the three packs")
        sys.exit(1)


def _setup_environment(mode: str, rerank: bool, chroma_dir: str) -> None:
    """Configure env vars and patch module-level constants for one cell."""
    if mode == "dense-only":
        os.environ["HYBRID_ENABLED"] = "false"
        os.environ["HYBRID_SPARSE_BACKEND"] = "bm25"
    elif mode == "hybrid_bm25":
        os.environ["HYBRID_ENABLED"] = "true"
        os.environ["HYBRID_SPARSE_BACKEND"] = "bm25"
    elif mode == "hybrid_native":
        os.environ["HYBRID_ENABLED"] = "true"
        os.environ["HYBRID_SPARSE_BACKEND"] = "native"
    else:
        raise ValueError(f"unknown mode: {mode}")

    os.environ["HYBRID_RRF_K"] = str(DEFAULT_RRF_K)
    os.environ["RERANK_MAX_FETCH"] = str(DEFAULT_RERANK_MAX_FETCH)
    os.environ["RERANK_FETCH_MULTIPLIER"] = str(DEFAULT_RERANK_FETCH_MULTIPLIER)
    os.environ["CHROMA_PERSIST_DIR"] = chroma_dir

    for mod_name in ("rag_mcp.ingestion", "rag_mcp.retrieval", "rag_mcp.config"):
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        if hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = chroma_dir
        if hasattr(mod, "HYBRID_ENABLED"):
            mod.HYBRID_ENABLED = (mode != "dense-only")
        if hasattr(mod, "HYBRID_SPARSE_BACKEND"):
            mod.HYBRID_SPARSE_BACKEND = os.environ["HYBRID_SPARSE_BACKEND"]
        if hasattr(mod, "RESOLVED_HYBRID_SPARSE_BACKEND"):
            mod.RESOLVED_HYBRID_SPARSE_BACKEND = os.environ["HYBRID_SPARSE_BACKEND"]

    # Reset reranker singleton.
    try:
        from rag_mcp.reranker import CrossEncoderReranker
        CrossEncoderReranker._instance = None  # type: ignore[attr-defined]
    except Exception:
        pass

    # Reset BM25 cache if present.
    try:
        from rag_mcp.sparse_retriever import BM25SparseRetriever  # type: ignore
        BM25SparseRetriever.clear_all_caches()  # type: ignore[attr-defined]
    except Exception:
        pass


def _ingest_for_mode(mode: str) -> str:
    """Ingest the corpus into a fresh ChromaDB for the given mode.

    Returns the ChromaDB directory path.
    """
    from rag_mcp.ingestion import ingest_path_async

    chroma_dir = tempfile.mkdtemp(prefix=f"rag_hybrid_{mode}_")
    _setup_environment(mode, rerank=False, chroma_dir=chroma_dir)
    print(f"  Ingesting corpus for mode={mode} into {chroma_dir}...")
    result = asyncio.run(ingest_path_async(str(CORPUS_DIR)))
    if result.get("status") != "ok":
        print(f"  ERROR: ingest failed for mode={mode}: {result.get('message')}")
        shutil.rmtree(chroma_dir, ignore_errors=True)
        sys.exit(1)
    print(f"    Indexed {result.get('chunks_created', 0)} chunks")
    return chroma_dir


def _evaluate_cell(
    mode: str, rerank: bool, queries: list[dict], chroma_dir: str
) -> CellResult:
    """Run all queries against one (mode, rerank) cell."""
    from rag_mcp.retrieval import search

    _setup_environment(mode, rerank, chroma_dir)
    cell = CellResult(mode=mode, rerank=rerank)

    # Warmup.
    for i in range(WARMUP_QUERIES):
        q = queries[i % len(queries)]
        search(
            query=q["query"],
            top_k=10,
            similarity_threshold=0.0,
            rerank=rerank,
            hybrid=(mode != "dense-only"),
            include_diagnostics=True,
        )

    # Measured queries.
    for qa in queries:
        query_text = qa["query"]
        expected_source = qa["expected_source"]
        expected_answer = qa.get("expected_answer")
        category = qa.get("category", "general")
        named_case = qa.get("named_case")

        started = time.perf_counter()
        results = search(
            query=query_text,
            top_k=10,
            similarity_threshold=0.0,
            rerank=rerank,
            hybrid=(mode != "dense-only"),
            include_diagnostics=True,
        )
        latency_ms = (time.perf_counter() - started) * 1000

        top_sources = [r.get("source", "") for r in results[:10]]
        top_scores = [r.get("score", 0.0) for r in results[:10]]

        # Fusion ranks for the gold chunk (if exposed by the retrieval layer).
        # Tier 3 task 6.x should attach `dense_rank` and `sparse_rank` to each
        # result dict when hybrid is active; otherwise we just record None.
        gold = next(
            (r for r in results if expected_source.lower() in r.get("source", "").lower()),
            None,
        )
        fusion_ranks = {
            "dense_rank": gold.get("dense_rank") if gold else None,
            "sparse_rank": gold.get("sparse_rank") if gold else None,
            "fused_rank": gold.get("fused_rank") if gold else None,
        }

        hit_rank = None
        for rank, source in enumerate(top_sources, start=1):
            if expected_source.lower() in source.lower():
                hit_rank = rank
                break

        answer_hit = False
        if expected_answer and results:
            top_text = results[0].get("text", "")
            answer_hit = expected_answer.lower() in top_text.lower()

        qr = QueryResult(
            query=query_text,
            expected_source=expected_source,
            expected_answer=expected_answer,
            category=category,
            named_case=named_case,
            top_k_sources=top_sources,
            top_k_scores=top_scores,
            fusion_ranks=fusion_ranks,
            hit_rank=hit_rank,
            hit_at_1=(hit_rank is not None and hit_rank <= 1),
            hit_at_5=(hit_rank is not None and hit_rank <= 5),
            recall_at_10=(hit_rank is not None and hit_rank <= 10),
            answer_hit=answer_hit,
            latency_ms=round(latency_ms, 2),
        )
        cell.queries.append(qr)

        if named_case:
            cell.named_cases[named_case] = {
                "hit_at_1": qr.hit_at_1,
                "hit_rank": qr.hit_rank,
                "fusion_ranks": qr.fusion_ranks,
            }

    cell.metrics_by_category = _aggregate_by_category(cell.queries)

    if cell.queries:
        latencies = sorted(q.latency_ms for q in cell.queries)
        cell.mean_latency_ms = round(statistics.mean(latencies), 2)
        cuts = statistics.quantiles(latencies, n=100, method="inclusive")
        cell.p95_latency_ms = round(cuts[94], 2)

    return cell


def _aggregate_by_category(queries: list[QueryResult]) -> dict[str, dict[str, float]]:
    """Compute per-category Hit@1 / Hit@5 / MRR@10 / Recall@10."""
    by_cat: dict[str, list[QueryResult]] = defaultdict(list)
    for q in queries:
        by_cat[q.category].append(q)

    metrics: dict[str, dict[str, float]] = {}
    for cat, items in by_cat.items():
        n = len(items)
        if n == 0:
            continue
        rr = [(1.0 / q.hit_rank) if q.hit_rank else 0.0 for q in items]
        metrics[cat] = {
            "n": n,
            "hit_at_1": round(sum(1 for q in items if q.hit_at_1) / n, 4),
            "hit_at_5": round(sum(1 for q in items if q.hit_at_5) / n, 4),
            "mrr_at_10": round(sum(rr) / n, 4),
            "recall_at_10": round(sum(1 for q in items if q.recall_at_10) / n, 4),
            "answer_accuracy": round(sum(1 for q in items if q.answer_hit) / n, 4),
        }
    return metrics


def _print_table(cells: list[CellResult]) -> None:
    """Print the cell × category comparison."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Hybrid Retrieval — Cell × Category")
        table.add_column("Cell", style="bold")
        table.add_column("Category")
        table.add_column("n", justify="right")
        table.add_column("Hit@1", justify="right")
        table.add_column("Hit@5", justify="right")
        table.add_column("MRR@10", justify="right")
        table.add_column("Recall@10", justify="right")
        table.add_column("P95 ms", justify="right")

        for cell in cells:
            cell_label = f"{cell.mode} / rerank={'on' if cell.rerank else 'off'}"
            for cat, m in cell.metrics_by_category.items():
                table.add_row(
                    cell_label,
                    cat,
                    str(int(m["n"])),
                    f"{100 * m['hit_at_1']:.1f}%",
                    f"{100 * m['hit_at_5']:.1f}%",
                    f"{m['mrr_at_10']:.3f}",
                    f"{100 * m['recall_at_10']:.1f}%",
                    f"{cell.p95_latency_ms:.0f}",
                )

        console.print()
        console.print(table)
        console.print()

        # Named cases.
        for cell in cells:
            if cell.named_cases:
                console.print(
                    f"  [bold]{cell.mode}/rerank={cell.rerank}[/bold] named cases: "
                    f"{cell.named_cases}"
                )
    except ImportError:
        for cell in cells:
            print(f"\n  {cell.mode} / rerank={'on' if cell.rerank else 'off'}")
            for cat, m in cell.metrics_by_category.items():
                print(
                    f"    {cat:<14} n={int(m['n']):>3} "
                    f"hit@1={100*m['hit_at_1']:>5.1f}% "
                    f"mrr={m['mrr_at_10']:.3f}"
                )


def _check_pass_criteria(cells: list[CellResult]) -> dict:
    """Apply the protocol's pass criteria."""
    grid: dict[tuple[str, bool], CellResult] = {(c.mode, c.rerank): c for c in cells}
    dense_off = grid.get(("dense-only", False))
    dense_on = grid.get(("dense-only", True))
    hybrid_off = grid.get(("hybrid_bm25", False))
    hybrid_on = grid.get(("hybrid_bm25", True))

    if not all([dense_off, dense_on, hybrid_off, hybrid_on]):
        return {"error": "incomplete cell grid"}

    # Colosseum named case.
    colosseum_hit = any(
        cell.named_cases.get("colosseum", {}).get("hit_at_1", False)
        for cell in cells
        if cell.mode != "dense-only"
    )

    # Per-category lifts at rerank-on.
    def m(cell: CellResult, cat: str, key: str) -> float:
        return cell.metrics_by_category.get(cat, {}).get(key, 0.0)

    rare_term_lift = (
        m(hybrid_on, "rare-term", "hit_at_1") - m(dense_on, "rare-term", "hit_at_1")
    )
    semantic_delta = (
        m(hybrid_on, "semantic", "hit_at_1") - m(dense_on, "semantic", "hit_at_1")
    )
    mixed_delta = (
        m(hybrid_on, "mixed", "hit_at_1") - m(dense_on, "mixed", "hit_at_1")
    )

    latency_ratio = (
        hybrid_on.p95_latency_ms / dense_on.p95_latency_ms
        if dense_on.p95_latency_ms
        else float("inf")
    )

    return {
        "colosseum_hit_top_1_under_hybrid": colosseum_hit,
        "rare_term_lift_pp": round(100 * rare_term_lift, 2),
        "rare_term_lift_pass": rare_term_lift >= 0.10,
        "semantic_delta_pp": round(100 * semantic_delta, 2),
        "semantic_non_regression_pass": semantic_delta >= -0.02,
        "mixed_delta_pp": round(100 * mixed_delta, 2),
        "mixed_non_regression_pass": mixed_delta >= 0.0,
        "latency_p95_ratio_hybrid_over_dense": round(latency_ratio, 3),
        "latency_pass": latency_ratio <= 1.5,
    }


def _recommendation(criteria: dict) -> str:
    """Decide whether to recommend flipping HYBRID_ENABLED to true."""
    if "error" in criteria:
        return f"FAIL: {criteria['error']}"
    flip_ok = all(
        [
            criteria.get("colosseum_hit_top_1_under_hybrid", False),
            criteria.get("rare_term_lift_pass", False),
            criteria.get("semantic_non_regression_pass", False),
            criteria.get("mixed_non_regression_pass", False),
            criteria.get("latency_pass", False),
        ]
    )
    if flip_ok:
        return (
            "RECOMMEND: follow-up change to flip HYBRID_ENABLED=true and "
            "consider promoting HYBRID_SPARSE_BACKEND=auto"
        )
    if not criteria.get("latency_pass", False):
        return (
            "PARTIAL: quality criteria met but latency budget breached — "
            "keep HYBRID_ENABLED=false default; document hybrid as a "
            "recommended opt-in"
        )
    return "FAIL: keep HYBRID_ENABLED=false; investigate per protocol's failure-mode guide"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--modes",
        type=str,
        default="dense-only,hybrid_bm25",
        help="Comma-separated list of modes to evaluate",
    )
    parser.add_argument(
        "--rerank-cross",
        action="store_true",
        help="Cross-product each mode with rerank on/off",
    )
    args = parser.parse_args()

    modes = [m.strip() for m in args.modes.split(",")]
    rerank_settings = [True, False] if args.rerank_cross else [True]

    print("Experiment 9: Hybrid Retrieval Quality")
    print("=" * 60)
    print(f"  Modes: {modes}")
    print(f"  Rerank settings: {rerank_settings}")
    print(f"  RRF k: {DEFAULT_RRF_K}")
    print(f"  Rerank pool: max_fetch={DEFAULT_RERANK_MAX_FETCH}, "
          f"multiplier={DEFAULT_RERANK_FETCH_MULTIPLIER}")
    print(f"  Warmup queries: {WARMUP_QUERIES} (discarded)")

    _validate_corpus()
    queries = _load_ground_truth()
    print(f"  Ground-truth queries: {len(queries)}")

    import rag_mcp.ingestion  # noqa: F401
    import rag_mcp.retrieval as retrieval

    if "hybrid" not in inspect.signature(retrieval.search).parameters:
        raise RuntimeError(
            "Experiment 9 requires retrieval.search(..., hybrid=...). "
            "Refusing to run hybrid cells through a dense-only signature."
        )

    # One ingest per mode (dense-only and hybrid_bm25 share ChromaDB shape but
    # we keep them separate for cleanliness; native gets its own).
    chroma_dirs: dict[str, str] = {}
    cells: list[CellResult] = []

    try:
        for mode in modes:
            chroma_dirs[mode] = _ingest_for_mode(mode)

        for mode in modes:
            for rerank in rerank_settings:
                print(f"\n  Cell: mode={mode}, rerank={rerank}")
                cell = _evaluate_cell(mode, rerank, queries, chroma_dirs[mode])
                cells.append(cell)
                print(
                    f"    mean={cell.mean_latency_ms}ms  "
                    f"P95={cell.p95_latency_ms}ms"
                )
    finally:
        for d in chroma_dirs.values():
            shutil.rmtree(d, ignore_errors=True)

    _print_table(cells)
    criteria = _check_pass_criteria(cells)
    recommendation = _recommendation(criteria)

    print("\n  Pass Criteria")
    print(f"  {'-' * 60}")
    for k, v in criteria.items():
        print(f"  {k}: {v}")
    print(f"\n  Recommendation: {recommendation}")

    output_path = EXPERIMENT_DIR / "eval_results.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "experiment": "hybrid-retrieval",
                "modes": modes,
                "rerank_settings": rerank_settings,
                "rrf_k": DEFAULT_RRF_K,
                "rerank_pool": {
                    "max_fetch": DEFAULT_RERANK_MAX_FETCH,
                    "multiplier": DEFAULT_RERANK_FETCH_MULTIPLIER,
                },
                "cells": [asdict(c) for c in cells],
                "pass_criteria": criteria,
                "recommendation": recommendation,
            },
            f,
            indent=2,
        )
    print(f"\n  Raw results saved to: {output_path}")


if __name__ == "__main__":
    main()
