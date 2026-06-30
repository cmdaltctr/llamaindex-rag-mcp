"""Summarise Experiment 10.1: DOC_SIMILARITY_THRESHOLD calibration.

Identifies the threshold that maximises modularity while keeping the
false-positive rate below 20%. Writes results.md and a summary JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def _compute_fp_rates(
    eval_results: dict[str, Any],
    manual_ratings: dict[str, Any] | None,
) -> dict[float, dict[str, Any]]:
    """Compute false-positive rates from manual ratings."""
    fp_by_threshold: dict[float, dict[str, Any]] = {}

    if manual_ratings is None:
        for result in eval_results.get("results", []):
            threshold = result["threshold"]
            fp_by_threshold[threshold] = {
                "rated_edges": 0,
                "noise_count": 0,
                "fp_rate": None,
                "note": "No manual ratings provided",
            }
        return fp_by_threshold

    ratings_by_threshold: dict[float, list[dict[str, Any]]] = {}
    for edge in manual_ratings.get("edges", []):
        threshold = edge.get("threshold")
        if threshold is not None:
            ratings_by_threshold.setdefault(threshold, []).append(edge)

    for threshold, edges in ratings_by_threshold.items():
        rated = [e for e in edges if e.get("rating") is not None]
        noise = sum(1 for e in rated if e["rating"] == "noise")
        fp_rate = noise / len(rated) if rated else None
        fp_by_threshold[threshold] = {
            "rated_edges": len(rated),
            "noise_count": noise,
            "fp_rate": round(fp_rate, 4) if fp_rate is not None else None,
        }

    # Fill in missing thresholds
    for result in eval_results.get("results", []):
        threshold = result["threshold"]
        if threshold not in fp_by_threshold:
            fp_by_threshold[threshold] = {
                "rated_edges": 0,
                "noise_count": 0,
                "fp_rate": None,
                "note": "No edges sampled for this threshold",
            }

    return fp_by_threshold


def _pass_criteria(
    eval_results: dict[str, Any],
    fp_by_threshold: dict[float, dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate pass gates and produce recommendation."""
    results = eval_results.get("results", [])
    if not results:
        return {"recommendation": "No results to evaluate.", "all_gates_pass": False}

    # Find modularity-optimal threshold
    best_modularity = max(r["modularity"] for r in results)
    optimal_threshold = next(r["threshold"] for r in results if r["modularity"] == best_modularity)

    # Check FP rate at optimal threshold
    optimal_fp = fp_by_threshold.get(optimal_threshold, {})
    optimal_fp_rate = optimal_fp.get("fp_rate")

    # Check current default (0.85)
    default_result = next((r for r in results if r["threshold"] == 0.85), None)
    default_fp = fp_by_threshold.get(0.85, {})
    default_fp_rate = default_fp.get("fp_rate")

    # Determine if 0.85 is within 10% of optimal modularity
    if default_result and best_modularity > 0:
        modularity_ratio = default_result["modularity"] / best_modularity
        default_within_10pct = modularity_ratio >= 0.90
    else:
        default_within_10pct = False

    # Determine recommended threshold
    fp_pass = optimal_fp_rate is not None and optimal_fp_rate < 0.20
    default_fp_pass = default_fp_rate is not None and default_fp_rate < 0.20

    if fp_pass and optimal_threshold != 0.85:
        recommendation = (
            f"RECOMMEND changing DOC_SIMILARITY_THRESHOLD from 0.85 to {optimal_threshold:.2f}. "
            f"Modularity is maximised at {optimal_threshold:.2f} ({best_modularity:.4f}) "
            f"with FP rate {optimal_fp_rate:.1%} (< 20%). "
            f"Draft ADR-023 amendment (separate change)."
        )
    elif fp_pass and optimal_threshold == 0.85:
        recommendation = (
            f"Current default (0.85) is optimal. Modularity={best_modularity:.4f}, "
            f"FP rate={optimal_fp_rate:.1%}. No change needed."
        )
    elif not fp_pass and default_fp_pass:
        recommendation = (
            f"Optimal modularity at {optimal_threshold:.2f} but FP rate too high "
            f"({optimal_fp_rate:.1%} ≥ 20%). Current default (0.85) is acceptable "
            f"with FP rate {default_fp_rate:.1%}. No change."
        )
    elif default_within_10pct and default_fp_pass:
        recommendation = (
            f"Current default (0.85) is within 10% of optimal modularity "
            f"and FP rate is acceptable. No change needed."
        )
    else:
        recommendation = (
            f"Results inconclusive. Optimal threshold={optimal_threshold:.2f} "
            f"but FP rates not yet rated or too high. "
            f"Complete manual ratings and re-run summarise."
        )

    return {
        "optimal_threshold": optimal_threshold,
        "optimal_modularity": best_modularity,
        "optimal_fp_rate": optimal_fp_rate,
        "default_modularity": default_result["modularity"] if default_result else None,
        "default_fp_rate": default_fp_rate,
        "default_within_10pct_of_optimal": default_within_10pct,
        "recommendation": recommendation,
        "all_gates_pass": fp_pass and (optimal_threshold == 0.85 or not default_fp_pass),
    }


def _write_results_md(
    eval_results: dict[str, Any],
    fp_by_threshold: dict[float, dict[str, Any]],
    pass_criteria: dict[str, Any],
    path: Path,
) -> None:
    lines = [
        "# Experiment 10.1 Results: DOC_SIMILARITY_THRESHOLD Calibration",
        "",
        f"**Recommendation:** {pass_criteria['recommendation']}",
        "",
        "## Corpus and setup",
        "",
        f"- Documents: {eval_results.get('settings', {}).get('doc_count')}",
        f"- Embedding model: {eval_results.get('settings', {}).get('embed_model')}",
        f"- Thresholds tested: {eval_results.get('settings', {}).get('thresholds')}",
        "",
        "## Per-threshold metrics",
        "",
        "| Threshold | Nodes | Edges | Sim Edges | Clusters | Mean Size | Modularity | FP Rate |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for result in eval_results.get("results", []):
        threshold = result["threshold"]
        fp = fp_by_threshold.get(threshold, {})
        fp_rate_str = f"{fp.get('fp_rate', 0):.1%}" if fp.get("fp_rate") is not None else "N/A"
        lines.append(
            f"| {threshold:.2f} | {result['node_count']} | {result['edge_count']} | "
            f"{result['similarity_edge_count']} | {result['cluster_count']} | "
            f"{result['mean_cluster_size']:.1f} | {result['modularity']:.4f} | "
            f"{fp_rate_str} |"
        )

    lines.extend([
        "",
        "## Pass gates",
        "",
        f"- **Optimal threshold**: {pass_criteria.get('optimal_threshold')}",
        f"- **Optimal modularity**: {pass_criteria.get('optimal_modularity')}",
        f"- **Optimal FP rate**: {pass_criteria.get('optimal_fp_rate')}",
        f"- **Default (0.85) modularity**: {pass_criteria.get('default_modularity')}",
        f"- **Default (0.85) FP rate**: {pass_criteria.get('default_fp_rate')}",
        f"- **Default within 10% of optimal**: {pass_criteria.get('default_within_10pct_of_optimal')}",
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=SCRIPT_DIR / "output" / "eval_results.json")
    parser.add_argument("--ratings", type=Path, default=SCRIPT_DIR / "output" / "manual_ratings.json")
    parser.add_argument("--output", type=Path, default=SCRIPT_DIR / "output" / "eval_results.summary.json")
    parser.add_argument("--results-md", type=Path, default=SCRIPT_DIR / "output" / "results.md")
    args = parser.parse_args()

    eval_results = json.loads(args.input.read_text(encoding="utf-8"))

    manual_ratings = None
    if args.ratings.exists():
        manual_ratings = json.loads(args.ratings.read_text(encoding="utf-8"))

    fp_by_threshold = _compute_fp_rates(eval_results, manual_ratings)
    pass_criteria = _pass_criteria(eval_results, fp_by_threshold)

    summary = {
        "experiment": eval_results.get("experiment"),
        "fp_by_threshold": fp_by_threshold,
        "pass_criteria": pass_criteria,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_md(eval_results, fp_by_threshold, pass_criteria, args.results_md)
    print(f"Summary written to {args.output}")
    print(f"Results report written to {args.results_md}")
    print(pass_criteria["recommendation"])


if __name__ == "__main__":
    main()
