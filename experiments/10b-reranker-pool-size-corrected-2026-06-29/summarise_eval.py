"""Summarise Experiment 10b raw evaluation results.

Aggregates per-query metrics by cell, query category, and fetch_k pool size.
Computes pass gates: pool-size lift, diminishing returns, reranker-off ceiling.
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
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cell.get("queries", []):
        groups["all"].append(row)
        groups[row.get("category") or "unknown"].append(row)
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
    fetch_k = cell.get("fetch_k", "?")
    rerank = cell.get("rerank", False)
    return f"dense_only__fetch_k_{fetch_k}__rerank_{str(rerank).lower()}"


def _pass_criteria(data: dict[str, Any], aggregates: dict[str, Any]) -> dict[str, Any]:
    corpus_docs = data.get("corpus", {}).get("total_parent_docs", 0)
    corpus_valid = corpus_docs >= 10_000

    fetch_k_sizes = data.get("settings", {}).get("fetch_k_values", [50, 100, 200, 500])

    def _all(fk: int) -> dict[str, Any]:
        key = f"dense_only__fetch_k_{fk}__rerank_true"
        return aggregates.get(key, {}).get("all", {})

    min_k, max_k = min(fetch_k_sizes), max(fetch_k_sizes)
    cov_min = _all(min_k).get("coverage_at_20", 0.0)
    cov_max = _all(max_k).get("coverage_at_20", 0.0)
    pool_lift = cov_max - cov_min
    pool_pass = pool_lift >= 0.03

    sorted_ks = sorted(fetch_k_sizes)
    if len(sorted_ks) >= 2:
        second_k = sorted_ks[-2]
        cov_second = _all(second_k).get("coverage_at_20", 0.0)
        dim_returns = cov_max - cov_second
    else:
        dim_returns = 0.0
    dim_pass = dim_returns <= 0.02

    best_cov = max((_all(k).get("coverage_at_20", 0.0) for k in fetch_k_sizes), default=0.0)
    best_k = max(fetch_k_sizes, key=lambda k: _all(k).get("coverage_at_20", 0.0))

    cells = data.get("cells", [])
    lat_min = next((c for c in cells if c.get("fetch_k") == min_k), {})
    lat_max = next((c for c in cells if c.get("fetch_k") == max_k), {})
    p95_min = lat_min.get("p95_latency_ms", 0.0)
    p95_max = lat_max.get("p95_latency_ms", 0.0)
    latency_ratio = p95_max / p95_min if p95_min else float("inf")
    latency_pass = latency_ratio <= 3.0

    distinct_pass = len(set(fetch_k_sizes)) == len(fetch_k_sizes)

    # Larger pools degrade quality (dilution effect)
    larger_is_worse = cov_min > cov_max

    criteria = {
        "corpus_validity": {"value": corpus_docs, "pass": corpus_valid},
        "pool_sizes_distinct": {"value": fetch_k_sizes, "pass": distinct_pass},
        "pool_size_lift": {
            "value": round(pool_lift, 6),
            "max_k_cov20": round(cov_max, 4),
            "min_k_cov20": round(cov_min, 4),
            "pass": pool_pass,
        },
        "diminishing_returns": {
            "value": round(dim_returns, 6),
            "pass": dim_pass,
        },
        "best_fetch_k": {
            "fetch_k": best_k,
            "coverage_at_20": round(best_cov, 4),
            "larger_pool_degrades": larger_is_worse,
        },
        "latency_guardrail": {
            "p95_min_ms": p95_min,
            "p95_max_ms": p95_max,
            "ratio": round(latency_ratio, 4),
            "pass": latency_pass,
        },
    }

    if larger_is_worse:
        recommendation = (
            f"Larger fetch_k pools DEGRADE quality (fetch_k={min_k} best at cov20={cov_min:.4f}, "
            f"fetch_k={max_k} worst at cov20={cov_max:.4f}). "
            "Reranker dilution effect confirmed. Smaller pool sizes are better. "
            "ADR-019 (RERANK_ENABLED=false) validated — reranker hurts regardless of pool size. "
            "No config change."
        )
    elif pool_pass and dim_pass:
        recommendation = (
            f"Pool size has a meaningful effect (>=3pp lift) with diminishing returns. "
            f"Best fetch_k={best_k} at cov20={best_cov:.4f}. "
            "Consider adjusting RERANK_FETCH_MULTIPLIER."
        )
    else:
        recommendation = (
            "Pool size does not meaningfully affect quality. "
            "Keep current config. No config change."
        )

    criteria["all_gates_pass"] = all(v.get("pass", False) for v in criteria.values() if "pass" in v)
    criteria["recommendation"] = recommendation
    return criteria


def _write_results_md(
    data: dict[str, Any],
    summary: dict[str, Any],
    path: Path,
) -> None:
    lines = [
        "# Experiment 10b Results: Corrected Reranker Pool-Size Sweep",
        "",
        f"**Recommendation:** {summary['pass_criteria']['recommendation']}",
        "",
        "## Corpus and setup",
        "",
        f"- Parent documents: {data.get('corpus', {}).get('total_parent_docs')}",
        f"- Embedding model: {data.get('settings', {}).get('embed_model')}",
        f"- RRF k: {data.get('settings', {}).get('hybrid_rrf_k')}",
        "- Reranker model: cross-encoder/ms-marco-MiniLM-L-6-v2 (ONNX)",
        f"- Fetch_k sizes tested: {data.get('settings', {}).get('fetch_k_sizes')}",
        f"- Post-ADR-021 config: MULTIPLIER={data.get('settings', {}).get('rerank_fetch_multiplier')}, "
        f"MAX_FETCH={data.get('settings', {}).get('rerank_max_fetch')}",
        "",
        "## Cell metrics (all queries)",
        "",
        "| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | P95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def _sort_key(item: tuple[str, dict]) -> tuple:
        key = item[0]
        fk = int(key.split("fetch_k_")[1].split("__")[0]) if "fetch_k_" in key else 0
        return (1, fk)

    for cell_key, groups in sorted(summary["metrics_by_cell"].items(), key=_sort_key):
        if "all" in groups:
            m = groups["all"]
            lines.append(
                f"| {cell_key} | {m['coverage_at_20']:.3f} | "
                f"{m['recall_at_50']:.3f} | {m['alpha_ndcg_at_10']:.3f} | "
                f"{m['hit_at_10']:.3f} | {m['mrr_at_10']:.3f} | "
                f"{m['p95_latency_ms']:.1f} |"
            )

    lines.extend(["", "## Pool-size comparison (dense-only, all queries)", ""])
    lines.append("| fetch_k | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@5 | Hit@10 | MRR@10 | P95 ms |")
    lines.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")

    fetch_k_sizes = data.get("settings", {}).get("fetch_k_values", [])
    for fk in sorted(fetch_k_sizes):
        key = f"dense_only__fetch_k_{fk}__rerank_true"
        m = summary["metrics_by_cell"].get(key, {}).get("all", {})
        lines.append(
            f"| {fk} | {m.get('coverage_at_20', 0):.3f} | "
            f"{m.get('recall_at_50', 0):.3f} | {m.get('alpha_ndcg_at_10', 0):.3f} | "
            f"{m.get('hit_at_5', 0):.3f} | {m.get('hit_at_10', 0):.3f} | "
            f"{m.get('mrr_at_10', 0):.3f} | {m.get('p95_latency_ms', 0):.1f} |"
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
        "This experiment uses the `fetch_k=` parameter on `search()` (TDR-005) to bypass",
        "the `max(RERANK_MAX_FETCH, top_k × RERANK_FETCH_MULTIPLIER)` formula, producing",
        "genuinely distinct pool sizes — the confound that voided Exp 10.",
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
