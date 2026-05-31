"""Summarise Experiment 9a raw evaluation results."""

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
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cell.get("queries", []):
        groups["all"].append(row)
        groups[row.get("category") or "unknown"].append(row)
        if row.get("source_kind") == "continuity-query":
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
    return f"{cell['mode']}__rerank_{str(cell['rerank']).lower()}"


def _bm25_contribution(dense: dict[str, Any], hybrid: dict[str, Any]) -> dict[str, Any]:
    dense_by_q = {row["query_id"]: row for row in dense.get("queries", [])}
    improved = 0
    contributed = 0
    examples: list[dict[str, Any]] = []
    for hrow in hybrid.get("queries", []):
        if hrow.get("category") != "identifier-heavy":
            continue
        drow = dense_by_q.get(hrow["query_id"])
        if not drow:
            continue
        if hrow["metrics"]["coverage_at_20"] <= drow["metrics"]["coverage_at_20"]:
            continue
        improved += 1
        has_sparse_help = False
        for result in hrow.get("top_results", [])[:20]:
            dense_rank = result.get("dense_rank")
            sparse_rank = result.get("sparse_rank")
            if sparse_rank is not None and (dense_rank is None or sparse_rank < dense_rank):
                has_sparse_help = True
                examples.append({
                    "query_id": hrow["query_id"],
                    "parent_id": result.get("parent_id"),
                    "dense_rank": dense_rank,
                    "sparse_rank": sparse_rank,
                    "fused_rank": result.get("fused_rank"),
                })
                break
        if has_sparse_help:
            contributed += 1
    ratio = contributed / improved if improved else 0.0
    return {
        "improved_identifier_queries": improved,
        "sparse_help_queries": contributed,
        "ratio": round(ratio, 6),
        "pass": ratio >= 0.25 if improved else False,
        "examples": examples[:10],
    }


def _pass_criteria(data: dict[str, Any], aggregates: dict[str, Any]) -> dict[str, Any]:
    cells = {_cell_key(cell): cell for cell in data.get("cells", [])}
    dense_on = aggregates.get("dense-only__rerank_true", {})
    hybrid_on = aggregates.get("hybrid_bm25__rerank_true", {})
    dense_cell = cells.get("dense-only__rerank_true", {})
    hybrid_cell = cells.get("hybrid_bm25__rerank_true", {})
    dense_all = dense_on.get("all", {})
    hybrid_all = hybrid_on.get("all", {})
    dense_ident = dense_on.get("identifier-heavy", {})
    hybrid_ident = hybrid_on.get("identifier-heavy", {})
    dense_sem = dense_on.get("semantic", {})
    hybrid_sem = hybrid_on.get("semantic", {})

    coverage_lift = hybrid_all.get("coverage_at_20", 0.0) - dense_all.get("coverage_at_20", 0.0)
    recall_lift = hybrid_all.get("recall_at_50", 0.0) - dense_all.get("recall_at_50", 0.0)
    identifier_lift = hybrid_ident.get("coverage_at_20", 0.0) - dense_ident.get("coverage_at_20", 0.0)
    semantic_delta = hybrid_sem.get("coverage_at_20", 0.0) - dense_sem.get("coverage_at_20", 0.0)
    latency_ratio = (
        hybrid_cell.get("p95_latency_ms", 0.0) / dense_cell.get("p95_latency_ms", 0.0)
        if dense_cell.get("p95_latency_ms", 0.0)
        else float("inf")
    )
    bm25 = _bm25_contribution(dense_cell, hybrid_cell) if dense_cell and hybrid_cell else {"pass": False}
    corpus_docs = data.get("corpus", {}).get("total_parent_docs", 0)

    continuity_dense = dense_on.get("continuity", {}).get("coverage_at_20", 0.0)
    continuity_hybrid = hybrid_on.get("continuity", {}).get("coverage_at_20", 0.0)

    criteria = {
        "corpus_validity": {"value": corpus_docs, "pass": corpus_docs >= 10_000},
        "production_coverage_lift": {"value": round(coverage_lift, 6), "pass": coverage_lift >= 0.05},
        "production_recall_lift": {"value": round(recall_lift, 6), "pass": recall_lift >= 0.05},
        "identifier_coverage_lift": {"value": round(identifier_lift, 6), "pass": identifier_lift >= 0.08},
        "semantic_guardrail_delta": {"value": round(semantic_delta, 6), "pass": semantic_delta >= -0.02},
        "latency_p95_ratio": {"value": round(latency_ratio, 6), "pass": latency_ratio <= 1.5},
        "bm25_contribution": bm25,
        "continuity_non_regression": {
            "dense_coverage_at_20": continuity_dense,
            "hybrid_coverage_at_20": continuity_hybrid,
            "pass": continuity_hybrid >= continuity_dense,
        },
    }
    criteria["all_gates_pass"] = all(
        value.get("pass", False) for value in criteria.values() if isinstance(value, dict) and "pass" in value
    )
    criteria["recommendation"] = (
        "RECOMMEND follow-up change to flip HYBRID_ENABLED=true"
        if criteria["all_gates_pass"]
        else "KEEP HYBRID_ENABLED=false default; hybrid remains opt-in"
    )
    return criteria


def _write_results_md(data: dict[str, Any], summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# Experiment 9a Results: Hybrid Retrieval on FreshStack LangChain",
        "",
        f"**Recommendation:** {summary['pass_criteria']['recommendation']}",
        "",
        "## Corpus and setup",
        "",
        f"- Parent documents: {data.get('corpus', {}).get('total_parent_docs')}",
        f"- Selection mode: {data.get('corpus', {}).get('selection_mode')}",
        f"- Embedding model: {data.get('settings', {}).get('embed_model')}",
        f"- RRF k: {data.get('settings', {}).get('hybrid_rrf_k')}",
        f"- Rerank pool: max_fetch={data.get('settings', {}).get('rerank_max_fetch')}, multiplier={data.get('settings', {}).get('rerank_fetch_multiplier')}",
        "",
        "## Cell metrics",
        "",
        "| Cell | Category | n | Coverage@20 | Recall@50 | alpha-nDCG@10 | Hit@10 | MRR@10 | P95 ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cell_key, groups in summary["metrics_by_cell"].items():
        for category, metrics in groups.items():
            lines.append(
                f"| {cell_key} | {category} | {metrics['n']} | "
                f"{metrics['coverage_at_20']:.3f} | {metrics['recall_at_50']:.3f} | "
                f"{metrics['alpha_ndcg_at_10']:.3f} | {metrics['hit_at_10']:.3f} | "
                f"{metrics['mrr_at_10']:.3f} | {metrics['p95_latency_ms']:.1f} |"
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
        "This run uses an experiment-specific direct Chroma ingestion helper to preserve FreshStack parent IDs.",
        "The exported Markdown corpus is retained under `corpus/`; raw metrics and Chroma indexes are under `output/`.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


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
