"""Summarise Experiment 10 raw evaluation results.

Aggregates per-query metrics by cell, query category, and reranker pool size.
Computes pass gates and writes a recommendation.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(statistics.quantiles(sorted(values), n=100, method="inclusive")[94], 2)


def _aggregate_cell(cell: dict[str, Any]) -> dict[str, Any]:
    """Aggregate per-query metrics into category groups."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cell.get("queries", []):
        groups["all"].append(row)
        groups[row.get("category") or "unknown"].append(row)
        # Avoid double-counting continuity rows: in this experiment they already
        # have category="continuity" as well as source_kind="continuity-query".
        if row.get("source_kind") == "continuity-query" and row.get("category") != "continuity":
            groups["continuity"].append(row)

    metrics: dict[str, Any] = {}
    for name, rows in groups.items():
        latencies = [float(row.get("latency_ms", 0.0)) for row in rows]
        metrics[name] = {
            "n": len(rows),
            "coverage_at_20": _mean([row["metrics"]["coverage_at_20"] for row in rows]),
            "recall_at_50": _mean([row["metrics"]["recall_at_50"] for row in rows]),
            "alpha_ndcg_at_10": _mean([row["metrics"]["alpha_ndcg_at_10"] for row in rows]),
            "hit_at_5": _mean([1.0 if row["metrics"]["hit_at_5"] else 0.0 for row in rows]),
            "hit_at_10": _mean([1.0 if row["metrics"]["hit_at_10"] else 0.0 for row in rows]),
            "mrr_at_10": _mean([row["metrics"]["mrr_at_10"] for row in rows]),
            "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "p95_latency_ms": _p95(latencies),
        }
    return metrics


def _cell_key(cell: dict[str, Any]) -> str:
    """Generate a unique cell key from mode, rerank, and pool size."""
    mode = cell["mode"]
    rerank = cell.get("rerank", False)
    pool = cell.get("rerank_max_fetch", 0)
    if not rerank:
        return f"{mode}__rerank_off"
    return f"{mode}__rerank_pool_{pool}"


# ---------------------------------------------------------------------------
# Pass criteria evaluation
# ---------------------------------------------------------------------------

def _pass_criteria(data: dict[str, Any], aggregates: dict[str, Any]) -> dict[str, Any]:
    """Evaluate all pass gates from the protocol."""
    corpus_docs = data.get("corpus", {}).get("total_parent_docs", 0)

    # Extract key cells
    dense_off = aggregates.get("dense-only__rerank_off", {})
    hybrid_off = aggregates.get("hybrid_bm25__rerank_off", {})
    dense_50 = aggregates.get("dense-only__rerank_pool_50", {})
    dense_200 = aggregates.get("dense-only__rerank_pool_200", {})
    dense_500 = aggregates.get("dense-only__rerank_pool_500", {})
    hybrid_50 = aggregates.get("hybrid_bm25__rerank_pool_50", {})
    hybrid_200 = aggregates.get("hybrid_bm25__rerank_pool_200", {})
    hybrid_500 = aggregates.get("hybrid_bm25__rerank_pool_500", {})

    # Get all-query metrics
    dense_off_all = dense_off.get("all", {})
    hybrid_off_all = hybrid_off.get("all", {})
    dense_50_all = dense_50.get("all", {})
    dense_200_all = dense_200.get("all", {})
    dense_500_all = dense_500.get("all", {})
    hybrid_50_all = hybrid_50.get("all", {})
    hybrid_200_all = hybrid_200.get("all", {})
    hybrid_500_all = hybrid_500.get("all", {})

    # Identifier-heavy metrics
    dense_50_ident = dense_50.get("identifier-heavy", {})
    dense_200_ident = dense_200.get("identifier-heavy", {})
    hybrid_50_ident = hybrid_50.get("identifier-heavy", {})
    hybrid_200_ident = hybrid_200.get("identifier-heavy", {})

    # 1. Corpus validity
    corpus_valid = corpus_docs >= 10_000

    # 2. Pool-size lift: hybrid pool=200 vs pool=50
    hybrid_pool_lift = (
        hybrid_200_all.get("coverage_at_20", 0.0)
        - hybrid_50_all.get("coverage_at_20", 0.0)
    )
    hybrid_pool_pass = hybrid_pool_lift >= 0.03

    # 3. Pool-size lift: dense pool=200 vs pool=50
    dense_pool_lift = (
        dense_200_all.get("coverage_at_20", 0.0)
        - dense_50_all.get("coverage_at_20", 0.0)
    )
    dense_pool_pass = dense_pool_lift >= 0.02

    # 4. Diminishing returns: hybrid pool=500 vs pool=200
    dim_returns = (
        hybrid_500_all.get("coverage_at_20", 0.0)
        - hybrid_200_all.get("coverage_at_20", 0.0)
    )
    dim_returns_pass = dim_returns <= 0.02

    # 5. Reranker-off ceiling check
    best_rerank_on_hybrid = max(
        hybrid_50_all.get("coverage_at_20", 0.0),
        hybrid_200_all.get("coverage_at_20", 0.0),
        hybrid_500_all.get("coverage_at_20", 0.0),
    )
    rerank_off_ceiling_pass = hybrid_off_all.get("coverage_at_20", 0.0) >= best_rerank_on_hybrid

    # 6. Latency guardrail: pool=200 P95 <= 3× pool=50 P95
    p50_hybrid = next(
        (c for c in data.get("cells", []) if c["mode"] == "hybrid_bm25" and c.get("rerank") and c.get("rerank_max_fetch") == 50),
        {},
    )
    p200_hybrid = next(
        (c for c in data.get("cells", []) if c["mode"] == "hybrid_bm25" and c.get("rerank") and c.get("rerank_max_fetch") == 200),
        {},
    )
    latency_50 = p50_hybrid.get("p95_latency_ms", 0.0)
    latency_200 = p200_hybrid.get("p95_latency_ms", 0.0)
    latency_ratio = latency_200 / latency_50 if latency_50 else float("inf")
    latency_pass = latency_ratio <= 3.0

    # 7. Continuity non-regression
    continuity_cells = {}
    for key, groups in aggregates.items():
        cont = groups.get("continuity", {})
        if cont:
            continuity_cells[key] = cont.get("coverage_at_20", 0.0)
    continuity_pass = all(v >= 0.90 for v in continuity_cells.values()) if continuity_cells else True

    criteria = {
        "corpus_validity": {"value": corpus_docs, "pass": corpus_valid},
        "hybrid_pool_lift_200_vs_50": {
            "value": round(hybrid_pool_lift, 6),
            "hybrid_200_cov20": round(hybrid_200_all.get("coverage_at_20", 0.0), 4),
            "hybrid_50_cov20": round(hybrid_50_all.get("coverage_at_20", 0.0), 4),
            "pass": hybrid_pool_pass,
        },
        "dense_pool_lift_200_vs_50": {
            "value": round(dense_pool_lift, 6),
            "dense_200_cov20": round(dense_200_all.get("coverage_at_20", 0.0), 4),
            "dense_50_cov20": round(dense_50_all.get("coverage_at_20", 0.0), 4),
            "pass": dense_pool_pass,
        },
        "diminishing_returns_500_vs_200": {
            "value": round(dim_returns, 6),
            "pass": dim_returns_pass,
        },
        "rerank_off_ceiling": {
            "rerank_off_cov20": round(hybrid_off_all.get("coverage_at_20", 0.0), 4),
            "best_rerank_on_cov20": round(best_rerank_on_hybrid, 4),
            "pass": rerank_off_ceiling_pass,
        },
        "latency_guardrail_pool200": {
            "pool_50_p95_ms": latency_50,
            "pool_200_p95_ms": latency_200,
            "ratio": round(latency_ratio, 4),
            "pass": latency_pass,
        },
        "continuity_non_regression": {
            "cells": continuity_cells,
            "pass": continuity_pass,
        },
    }

    # Determine recommendation
    all_pass = all(
        v.get("pass", False) for v in criteria.values() if isinstance(v, dict) and "pass" in v
    )
    if all_pass:
        recommendation = (
            "RECOMMEND updating RERANK_MAX_FETCH to 200 "
            "(or the best-performing pool size). Update ADR-018."
        )
    elif hybrid_pool_pass and not latency_pass:
        recommendation = (
            "Pool size improves quality but latency is too high. "
            "Keep reranking opt-in for technical workloads. "
            "Consider faster reranker model."
        )
    elif not hybrid_pool_pass and not dense_pool_pass:
        recommendation = (
            "RECOMMEND disabling reranking for technical/hybrid workloads. "
            "The cross-encoder model is fundamentally mismatched. "
            "Propose model research as follow-up."
        )
    else:
        recommendation = (
            "PARTIAL improvement from larger pool. "
            "Document the trade-off. Keep reranking opt-in for technical workloads."
        )

    criteria["all_gates_pass"] = all_pass
    criteria["recommendation"] = recommendation
    return criteria


# ---------------------------------------------------------------------------
# Results report writer
# ---------------------------------------------------------------------------

def _write_results_md(
    data: dict[str, Any],
    summary: dict[str, Any],
    path: Path,
) -> None:
    """Write a human-readable results.md report."""
    lines = [
        "# Experiment 10 Results: Reranker Technical Workload Calibration",
        "",
        f"**Recommendation:** {summary['pass_criteria']['recommendation']}",
        "",
        "## Corpus and setup",
        "",
        f"- Parent documents: {data.get('corpus', {}).get('total_parent_docs')}",
        f"- Selection mode: {data.get('corpus', {}).get('selection_mode')}",
        f"- Embedding model: {data.get('settings', {}).get('embed_model')}",
        f"- RRF k: {data.get('settings', {}).get('hybrid_rrf_k')}",
        f"- Reranker model: cross-encoder/ms-marco-MiniLM-L-6-v2 (ONNX)",
        f"- Reranker pools tested: {data.get('settings', {}).get('reranker_pools')}",
        f"- Fetch multiplier: {data.get('settings', {}).get('rerank_fetch_multiplier')}",
        "",
        "## Cell metrics",
        "",
        "| Cell | Category | n | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | P95 ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    # Sort cells: rerank-off first, then by pool size
    def _sort_key(item: tuple[str, dict]) -> tuple:
        key = item[0]
        if "rerank_off" in key:
            return (0, key)
        pool = int(key.split("pool_")[-1]) if "pool_" in key else 0
        return (1, pool)

    for cell_key, groups in sorted(summary["metrics_by_cell"].items(), key=_sort_key):
        for category, metrics in sorted(groups.items()):
            lines.append(
                f"| {cell_key} | {category} | {metrics['n']} | "
                f"{metrics['coverage_at_20']:.3f} | {metrics['recall_at_50']:.3f} | "
                f"{metrics['alpha_ndcg_at_10']:.3f} | {metrics['hit_at_10']:.3f} | "
                f"{metrics['mrr_at_10']:.3f} | {metrics['p95_latency_ms']:.1f} |"
            )

    lines.extend(["", "## Pool-size comparison (all queries)", ""])
    lines.append(
        "| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | P95 ms |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")

    for cell_key, groups in sorted(summary["metrics_by_cell"].items(), key=_sort_key):
        if "all" in groups:
            m = groups["all"]
            lines.append(
                f"| {cell_key} | {m['coverage_at_20']:.3f} | "
                f"{m['recall_at_50']:.3f} | {m['alpha_ndcg_at_10']:.3f} | "
                f"{m['hit_at_10']:.3f} | {m['mrr_at_10']:.3f} | "
                f"{m['p95_latency_ms']:.1f} |"
            )

    lines.extend(["", "## Pass gates", ""])
    for name, value in summary["pass_criteria"].items():
        if name in {"recommendation", "all_gates_pass"}:
            continue
        lines.append(f"- **{name}**: `{json.dumps(value, ensure_ascii=False)}`")

    lines.extend([
        "",
        "## Notes",
        "",
        "This experiment reuses the FreshStack LangChain corpus from Experiment 9a.",
        "The corpus, ground truth, and ChromaDB indexes are identical.",
        "Only the reranker pool sizing (`RERANK_MAX_FETCH`) varies between cells.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=SCRIPT_DIR / "output" / "eval_results.json")
    parser.add_argument("--output", type=Path, default=SCRIPT_DIR / "output" / "eval_results.summary.json")
    parser.add_argument("--results-md", type=Path, default=SCRIPT_DIR / "output" / "results.md")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    aggregates = {_cell_key(cell): _aggregate_cell(cell) for cell in data.get("cells", [])}
    summary = {
        "experiment": data.get("experiment"),
        "metrics_by_cell": aggregates,
        "pass_criteria": _pass_criteria(data, aggregates),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_md(data, summary, args.results_md)
    print(f"Summary written to {args.output}")
    print(f"Results report written to {args.results_md}")
    print(summary["pass_criteria"]["recommendation"])


if __name__ == "__main__":
    main()
