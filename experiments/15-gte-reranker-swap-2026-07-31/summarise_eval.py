"""Summarise Experiment 15 results.

Aggregates raw eval_results.json into per-cell metrics, computes pass gates
from the protocol thresholds, and writes results.md + summary JSON.
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
    if len(values) < 2:
        return round(values[0], 2)
    return round(statistics.quantiles(sorted(values), n=100, method="inclusive")[94], 2)


def _aggregate_cell(cell: dict[str, Any]) -> dict[str, Any]:
    """Aggregate metrics by category within a cell."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cell.get("queries", []):
        groups["all"].append(row)
        groups[row.get("category") or "unknown"].append(row)

    metrics: dict[str, Any] = {}
    for name, rows in groups.items():
        latencies = [float(row.get("latency_ms", 0.0)) for row in rows]
        metrics[name] = {
            "n": len(rows),
            "coverage_at_20": _mean(
                [row["metrics"].get("coverage_at_20", 0.0) for row in rows]
            ),
            "recall_at_50": _mean(
                [row["metrics"].get("recall_at_50", 0.0) for row in rows]
            ),
            "alpha_ndcg_at_10": _mean(
                [row["metrics"].get("alpha_ndcg_at_10", 0.0) for row in rows]
            ),
            "hit_at_1": _mean(
                [1.0 if row["metrics"].get("hit_at_1") else 0.0 for row in rows]
            ),
            "hit_at_5": _mean(
                [1.0 if row["metrics"].get("hit_at_5") else 0.0 for row in rows]
            ),
            "hit_at_10": _mean(
                [1.0 if row["metrics"].get("hit_at_10") else 0.0 for row in rows]
            ),
            "mrr_at_10": _mean(
                [row["metrics"].get("mrr_at_10", 0.0) for row in rows]
            ),
            "mean_latency_ms": round(statistics.mean(latencies), 2)
            if latencies
            else 0.0,
            "p95_latency_ms": _p95(latencies),
        }
    return metrics


def _pass_criteria(aggregates: dict[str, Any]) -> dict[str, Any]:
    """Compute pass gates from protocol thresholds."""
    off = aggregates.get("hybrid_off", {}).get("all", {})
    minilm = aggregates.get("hybrid_minilm", {}).get("all", {})
    gte = aggregates.get("hybrid_gte", {}).get("all", {})

    gte_coverage = gte.get("coverage_at_20", 0.0)
    off_coverage = off.get("coverage_at_20", 0.0)
    minilm_coverage = minilm.get("coverage_at_20", 0.0)

    coverage_lift = gte_coverage - off_coverage
    gte_vs_minilm = gte_coverage - minilm_coverage

    off_p95 = off.get("p95_latency_ms", 0.0)
    gte_p95 = gte.get("p95_latency_ms", 0.0)
    latency_ratio = gte_p95 / off_p95 if off_p95 else float("inf")

    criteria = {
        "gte_beats_baseline_0_738": {
            "value": round(gte_coverage, 6),
            "threshold": 0.738,
            "pass": gte_coverage >= 0.738,
        },
        "gte_beats_rerank_off": {
            "value": round(gte_coverage, 6),
            "baseline": round(off_coverage, 6),
            "pass": gte_coverage >= off_coverage,
        },
        "gte_beats_minilm": {
            "value": round(gte_coverage, 6),
            "minilm": round(minilm_coverage, 6),
            "pass": gte_coverage >= minilm_coverage,
        },
        "coverage_lift_3pp": {
            "value": round(coverage_lift, 6),
            "threshold": 0.03,
            "pass": coverage_lift >= 0.03,
        },
        "latency_guardrail_3x": {
            "value": round(latency_ratio, 6),
            "threshold": 3.0,
            "pass": latency_ratio <= 3.0,
        },
    }

    # Load logit distribution data if available.
    logit_path = SCRIPT_DIR / "output" / "logit_distributions.json"
    if logit_path.exists():
        logit_data = json.loads(logit_path.read_text(encoding="utf-8"))
        ratio = logit_data.get("std_dev_ratio")
        if ratio is not None:
            criteria["logit_std_dev_ratio"] = {
                "value": ratio,
                "threshold": 2.0,
                "pass": ratio <= 2.0,
                "recalibration_needed": ratio > 2.0,
            }

    criteria["all_gates_pass"] = all(
        v.get("pass", False) for v in criteria.values() if isinstance(v, dict)
    )

    # Recommendation logic.
    quality_gates = [
        criteria["gte_beats_baseline_0_738"]["pass"],
        criteria["gte_beats_rerank_off"]["pass"],
        criteria["gte_beats_minilm"]["pass"],
    ]
    if all(quality_gates) and criteria["latency_guardrail_3x"]["pass"]:
        criteria["recommendation"] = (
            "ADOPT gte-reranker-modernbert-base as default. "
            "Flip ADR-028 to Accepted."
        )
    elif criteria["gte_beats_rerank_off"]["pass"] and not criteria[
        "gte_beats_minilm"
    ]["pass"]:
        criteria["recommendation"] = (
            "INCONCLUSIVE — gte beats rerank-off but not MiniLM. "
            "Keep MiniLM as default."
        )
    elif not criteria["gte_beats_rerank_off"]["pass"]:
        criteria["recommendation"] = (
            "REJECT — gte does not beat rerank-off baseline. "
            "Document negative result."
        )
    else:
        criteria["recommendation"] = (
            "PARTIAL — some gates passed. Review individual criteria."
        )

    return criteria


def _write_results_md(
    data: dict[str, Any], summary: dict[str, Any], path: Path
) -> None:
    lines = [
        "# Experiment 15: gte-reranker-modernbert-base A/B Comparison",
        "",
        f"**Recommendation:** {summary['pass_criteria']['recommendation']}",
        "",
        "## Executive summary",
        "",
        "TODO: Summarise the bottom line in 1–3 paragraphs after running.",
        "",
        "## Cell metrics (all queries)",
        "",
        "| Cell | Reranker | Coverage@20 | Hit@1 | Hit@5 | Hit@10 | MRR@10 | P95 ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    cell_labels = {
        "hybrid_off": "rerank-off",
        "hybrid_minilm": "MiniLM",
        "hybrid_gte": "gte-reranker",
    }

    for cell_key in ("hybrid_off", "hybrid_minilm", "hybrid_gte"):
        groups = summary["metrics_by_cell"].get(cell_key, {})
        m = groups.get("all", {})
        label = cell_labels.get(cell_key, cell_key)
        lines.append(
            f"| {label} | {m.get('reranker_model', 'N/A')} | "
            f"{m.get('coverage_at_20', 0.0):.4f} | "
            f"{m.get('hit_at_1', 0.0):.4f} | "
            f"{m.get('hit_at_5', 0.0):.4f} | "
            f"{m.get('hit_at_10', 0.0):.4f} | "
            f"{m.get('mrr_at_10', 0.0):.4f} | "
            f"{m.get('p95_latency_ms', 0.0):.0f} |"
        )

    # Identifier-heavy subset.
    lines.extend(
        [
            "",
            "## Identifier-heavy subset (200 queries)",
            "",
            "| Cell | Coverage@20 | Hit@1 | Hit@5 | MRR@10 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for cell_key in ("hybrid_off", "hybrid_minilm", "hybrid_gte"):
        groups = summary["metrics_by_cell"].get(cell_key, {})
        m = groups.get("identifier-heavy", {})
        label = cell_labels.get(cell_key, cell_key)
        lines.append(
            f"| {label} | "
            f"{m.get('coverage_at_20', 0.0):.4f} | "
            f"{m.get('hit_at_1', 0.0):.4f} | "
            f"{m.get('hit_at_5', 0.0):.4f} | "
            f"{m.get('mrr_at_10', 0.0):.4f} |"
        )

    # Pass gates.
    lines.extend(["", "## Pass gates", ""])
    for name, value in summary["pass_criteria"].items():
        if name in {"recommendation", "all_gates_pass"}:
            continue
        lines.append(f"- **{name}**: `{json.dumps(value, ensure_ascii=False)}`")

    lines.extend(
        [
            "",
            "## Conclusion / decision",
            "",
            "TODO: State what ships, what does not ship, and any follow-up experiment.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise Experiment 15")
    parser.add_argument(
        "--input",
        type=Path,
        default=SCRIPT_DIR / "output" / "eval_results.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SCRIPT_DIR / "output" / "eval_results.summary.json",
    )
    parser.add_argument(
        "--results-md",
        type=Path,
        default=SCRIPT_DIR / "results.md",
    )
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    aggregates = {
        cell["cell_id"]: _aggregate_cell(cell) for cell in data.get("cells", [])
    }

    # Attach reranker model info to the "all" group for the results table.
    for cell in data.get("cells", []):
        cell_id = cell["cell_id"]
        if cell_id in aggregates and "all" in aggregates[cell_id]:
            aggregates[cell_id]["all"]["reranker_model"] = cell.get(
                "reranker_model"
            ) or "N/A"

    summary = {
        "experiment": data.get("experiment"),
        "metrics_by_cell": aggregates,
        "pass_criteria": _pass_criteria(aggregates),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_results_md(data, summary, args.results_md)
    print(f"Summary written to {args.output}")
    print(f"Results report written to {args.results_md}")
    print(summary["pass_criteria"]["recommendation"])


if __name__ == "__main__":
    main()
