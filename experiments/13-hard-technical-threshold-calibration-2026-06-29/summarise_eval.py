"""Summarise Experiment 13 (v2.0): threshold-policy contrasts, paired CIs.

Compares each policy cell (``rerank=None`` at a swept threshold) against
the SAME-fraction reference envelope arms (``reranker_off`` floor,
``reranker_on`` ceiling), paired by ``query_id`` on the fixed fraction
blocks (D18): semantic-benefit contrasts (policy vs off) and
technical-guard contrasts (policy vs on/off), split by query type, with
paired bootstrap confidence intervals from ``_lib.stats`` (D16).
Warm-up rows are excluded; non-complete cells are listed as invalid and
never aggregated.  Factor levels come from ``plan.json`` (D15).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SEED = 20260629
PRIMARY_METRIC = "coverage_at_20"
QUERY_TYPES = ("technical", "semantic")
REFERENCE_ARMS = ("reranker_off", "reranker_on")


def _plan_levels(plan: dict[str, Any], name: str) -> list[Any]:
    """Return one manipulated factor's declared levels from plan.json."""
    for factor in plan.get("manipulated_factors", []):
        if factor.get("name") == name:
            return list(factor["levels"])
    raise SystemExit(f"plan.json lacks manipulated factor {name!r}")


def _measured_metric_by_query(cell: dict[str, Any], query_type: str) -> dict[str, float]:
    """Per-query primary metric for one query type, warm-up excluded."""
    from experiments._lib.stats import split_warmup

    _, measured = split_warmup(cell["per_query"])
    values: dict[str, float] = {}
    for row in measured:
        if row["metrics"].get("query_type") != query_type:
            continue
        value = row["metrics"].get(PRIMARY_METRIC)
        if value is not None:
            values[row["query_id"]] = float(value)
    return values


def _contrast(
    policy_cell: dict[str, Any],
    reference_cell: dict[str, Any],
    *,
    fraction: Any,
    threshold: Any,
    query_type: str,
    reference_arm: str,
) -> dict[str, Any] | None:
    """Paired bootstrap contrast of one policy cell vs one reference arm."""
    from experiments._lib.stats import paired_bootstrap_ci

    policy_values = _measured_metric_by_query(policy_cell, query_type)
    reference_values = _measured_metric_by_query(reference_cell, query_type)
    paired_ids = sorted(set(policy_values) & set(reference_values))
    if not paired_ids:
        return None
    policy_series = [policy_values[qid] for qid in paired_ids]
    reference_series = [reference_values[qid] for qid in paired_ids]
    ci = paired_bootstrap_ci(policy_series, reference_series, seed=SEED)
    return {
        "fraction": fraction,
        "threshold": threshold,
        "query_type": query_type,
        "comparison": f"policy_vs_{reference_arm}",
        "n": int(ci["n"]),
        "policy_mean": sum(policy_series) / len(policy_series),
        "reference_mean": sum(reference_series) / len(reference_series),
        "delta": ci["delta"],
        "ci_low": ci["ci_low"],
        "ci_high": ci["ci_high"],
        "confidence": ci["confidence"],
    }


def _write_results_md(summary: dict[str, Any], path: Path) -> None:
    """Write a compact human-readable contrast table (results.md)."""
    lines = [
        "# Experiment 13 Results (v2.0): threshold policy vs reference envelope",
        "",
        f"**Primary metric:** {summary['primary_metric']} (paired by query_id",
        f"on fixed fraction blocks; bootstrap seed {summary['bootstrap_seed']})",
        "",
        "| Fraction | Threshold | Query type | Comparison | N | Policy | Reference | Delta | 95% CI |",
        "| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for c in summary["contrasts"]:
        lines.append(
            f"| {c['fraction']} | {c['threshold']} | {c['query_type']} "
            f"| {c['comparison']} | {c['n']} | {c['policy_mean']:.4f} "
            f"| {c['reference_mean']:.4f} | {c['delta']:+.4f} "
            f"| [{c['ci_low']:+.4f}, {c['ci_high']:+.4f}] |"
        )
    if summary["invalid_cells"]:
        lines.extend(["", "## Invalid / incomplete cells (never aggregated)", ""])
        for cell in summary["invalid_cells"]:
            lines.append(f"- `{cell['cell_id']}` ({cell['status']}): {cell['reason']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=SCRIPT_DIR / "output" / "eval_results.json")
    parser.add_argument(
        "--output", type=Path, default=SCRIPT_DIR / "output" / "eval_results.summary.json"
    )
    parser.add_argument("--results-md", type=Path, default=SCRIPT_DIR / "output" / "results.md")
    args = parser.parse_args()

    plan_path = SCRIPT_DIR / "plan.json"
    if not plan_path.exists():
        raise SystemExit(f"Machine-readable plan missing: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    thresholds = _plan_levels(plan, "threshold")
    fractions = _plan_levels(plan, "fraction")

    data = json.loads(args.input.read_text(encoding="utf-8"))
    raw_cells = data.get("cells", [])
    cells = {c["cell_id"]: c for c in raw_cells if "cell_id" in c}
    invalid_cells = [
        {
            "cell_id": c.get("cell_id", c.get("cell")),
            "status": c.get("status"),
            "reason": c.get("reason"),
        }
        for c in raw_cells
        if c.get("status") != "complete"
    ]

    contrasts: list[dict[str, Any]] = []
    for fraction in fractions:
        references: dict[str, dict[str, Any]] = {}
        for arm in REFERENCE_ARMS:
            suffix = "off" if arm == "reranker_off" else "on"
            reference = cells.get(f"thr_ref_frac_{fraction}__{suffix}")
            if reference is not None and reference.get("status") == "complete":
                references[arm] = reference
        for threshold in thresholds:
            policy = cells.get(f"thr_{threshold}_frac_{fraction}__policy")
            if policy is None or policy.get("status") != "complete":
                continue
            for query_type in QUERY_TYPES:
                for arm, reference in references.items():
                    record = _contrast(
                        policy,
                        reference,
                        fraction=fraction,
                        threshold=threshold,
                        query_type=query_type,
                        reference_arm=arm,
                    )
                    if record is not None:
                        contrasts.append(record)

    summary = {
        "experiment_id": data.get("experiment_id"),
        "protocol_version": data.get("protocol_version"),
        "primary_metric": PRIMARY_METRIC,
        "bootstrap_seed": SEED,
        "n_contrasts": len(contrasts),
        "contrasts": contrasts,
        "invalid_cells": invalid_cells,
        "interpretation": (
            "policy_vs_reranker_off > 0 preserves the reranker's benefit on "
            "semantic queries; policy_vs_reranker_on on technical queries "
            "quantifies how close the policy stays to the no-rerank floor "
            "relative to the forced-rerank ceiling."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_md(summary, args.results_md)
    print(f"Summary written to {args.output}")
    print(f"Results report written to {args.results_md}")
    print(f"Contrasts: {len(contrasts)}; invalid cells: {len(invalid_cells)}")


if __name__ == "__main__":
    main()
