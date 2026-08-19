"""Summarise Experiment 10b v2: D17 contrasts with paired bootstrap CIs.

Reads ``output/eval_results.json`` produced by the repaired ``run_eval.py``
and writes ``output/eval_results.summary.json`` (plus ``results.md``) with:

- per-cell aggregates computed from MEASURED rows only — warm-up rows are
  split out via ``experiments._lib.stats.split_warmup`` (D16);
- the pre-registered D17 contrasts (H1a/H1b current policy, H2 best-on
  ceiling, H3/H4 pool sensitivity, H5 hybrid-off lift) with 95% paired
  bootstrap confidence intervals from ``paired_bootstrap_ci``
  (seed 20260819), paired by ``query_id``;
- invalid/incomplete cells reported as such — never aggregated.

Contrasts referencing cells that are absent or not complete are listed
under ``missing_cells`` instead of being computed.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from experiments._lib.stats import paired_bootstrap_ci, split_warmup  # noqa: E402

# Same seed as the runner's counterbalanced schedule (protocol v2.0).
SEED = 20260819
PRIMARY_METRIC = "coverage_at_20"


def _measured_by_query(cell: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return ``{query_id: measured row}`` for a complete cell."""
    _, measured = split_warmup(cell["per_query"])
    return {str(row["query_id"]): row for row in measured}


def _cell_aggregate(cell: dict[str, Any]) -> dict[str, Any]:
    """Aggregate one complete cell from its measured rows only."""
    _, measured = split_warmup(cell["per_query"])
    rows = list(measured)
    n = len(rows)
    agg: dict[str, Any] = {"n_measured": n}
    for key in ("coverage_at_20", "recall_at_50", "alpha_ndcg_at_10", "mrr_at_10"):
        values = [float(row["metrics"][key]) for row in rows]
        agg[key] = round(sum(values) / n, 6) if n else 0.0
    for key in ("hit_at_5", "hit_at_10"):
        values = [1.0 if row["metrics"][key] else 0.0 for row in rows]
        agg[key] = round(sum(values) / n, 6) if n else 0.0
    latencies = [float(row["latency_ms"]) for row in rows]
    agg["mean_latency_ms"] = round(statistics.mean(latencies), 2) if latencies else 0.0
    if len(latencies) >= 2:
        agg["p95_latency_ms"] = round(
            statistics.quantiles(sorted(latencies), n=100, method="inclusive")[94], 2
        )
    else:
        agg["p95_latency_ms"] = round(latencies[0], 2) if latencies else 0.0
    return agg


def _paired_contrast(
    a_cell: dict[str, Any],
    b_cell: dict[str, Any],
    *,
    label: str,
    metric: str = PRIMARY_METRIC,
    post_hoc: bool = False,
) -> dict[str, Any]:
    """Paired bootstrap CI for ``a - b`` on one metric, paired by query_id."""
    a_rows = _measured_by_query(a_cell)
    b_rows = _measured_by_query(b_cell)
    shared = sorted(set(a_rows) & set(b_rows))
    if not shared:
        return {
            "label": label,
            "a": a_cell["cell_id"],
            "b": b_cell["cell_id"],
            "metric": metric,
            "status": "unavailable",
            "reason": "no query_id measured in both cells",
        }
    a_values = [float(a_rows[qid]["metrics"][metric]) for qid in shared]
    b_values = [float(b_rows[qid]["metrics"][metric]) for qid in shared]
    ci = paired_bootstrap_ci(a_values, b_values, seed=SEED)
    return {
        "label": label,
        "a": a_cell["cell_id"],
        "b": b_cell["cell_id"],
        "metric": metric,
        "status": "ok",
        "selected_post_hoc": post_hoc,
        "delta": ci["delta"],
        "ci_low": ci["ci_low"],
        "ci_high": ci["ci_high"],
        "n": ci["n"],
        "confidence": ci["confidence"],
    }


def _build_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Classify cells and compute the pre-registered contrasts."""
    complete: dict[str, dict[str, Any]] = {}
    invalid: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    for cell in data.get("cells", []):
        status = cell.get("status")
        if status == "complete":
            complete[str(cell["cell_id"])] = cell
        elif status == "invalid":
            invalid.append({"cell_id": cell.get("cell_id"), "reason": cell.get("reason")})
        else:
            incomplete.append(
                {"cell_id": cell.get("cell_id"), "status": status, "reason": cell.get("reason")}
            )

    missing: list[dict[str, Any]] = []
    contrasts: list[dict[str, Any]] = []

    def _require(cell_id: str, label: str) -> dict[str, Any] | None:
        if cell_id in complete:
            return complete[cell_id]
        missing.append({"hypothesis": label, "cell_id": cell_id})
        return None

    # H1a/H1b — current policy: reranker-on at the production pool (150)
    # versus the mode's reranker-off ceiling.
    for label, on_id, off_id in (
        ("H1a", "dense_on_150", "dense_off"),
        ("H1b", "hybrid_on_150", "hybrid_off"),
    ):
        on_cell = _require(on_id, label)
        off_cell = _require(off_id, label)
        if on_cell is not None and off_cell is not None:
            contrasts.append(_paired_contrast(on_cell, off_cell, label=label))

    # H2 — best reranker-on pool versus the off ceiling, per mode.  The
    # pool is selected after seeing results, so the optimism risk is
    # flagged rather than hidden (D17 template section 14).
    for prefix, off_id in (("dense", "dense_off"), ("hybrid", "hybrid_off")):
        on_cells = [c for cid, c in complete.items() if cid.startswith(f"{prefix}_on_")]
        off_cell = _require(off_id, f"H2_{prefix}")
        if on_cells and off_cell is not None:
            best = max(on_cells, key=lambda c: _cell_aggregate(c)["coverage_at_20"])
            contrasts.append(
                _paired_contrast(best, off_cell, label=f"H2_{prefix}_best_vs_off", post_hoc=True)
            )

    # H3/H4 — pool sensitivity and diminishing returns on hybrid rerank-on.
    for label, a_id, b_id in (
        ("H3", "hybrid_on_500", "hybrid_on_50"),
        ("H4", "hybrid_on_500", "hybrid_on_200"),
    ):
        a_cell = _require(a_id, label)
        b_cell = _require(b_id, label)
        if a_cell is not None and b_cell is not None:
            contrasts.append(_paired_contrast(a_cell, b_cell, label=label))

    # H5 — hybrid-off lift over dense-off.
    a_cell = _require("hybrid_off", "H5")
    b_cell = _require("dense_off", "H5")
    if a_cell is not None and b_cell is not None:
        contrasts.append(_paired_contrast(a_cell, b_cell, label="H5"))

    per_cell: dict[str, dict[str, Any]] = {}
    for cid, cell in complete.items():
        entry = _cell_aggregate(cell)
        entry["factors"] = cell.get("factors")
        per_cell[cid] = entry

    return {
        "experiment": data.get("experiment"),
        "primary_metric": PRIMARY_METRIC,
        "per_cell": per_cell,
        "contrasts": contrasts,
        "missing_cells": missing,
        "invalid_cells": invalid,
        "incomplete_cells": incomplete,
    }


def _write_results_md(summary: dict[str, Any], path: Path) -> None:
    """Write the human-readable H1-H5 report."""
    lines = [
        "# Experiment 10b v2 Results: combined D17 factorial",
        "",
        "All contrasts are paired by query_id on Coverage@20 with a 95%",
        "bootstrap CI (10,000 resamples, seed 20260819). Warm-up rows are",
        "excluded from every aggregate.",
        "",
        "## Contrasts",
        "",
        "| Hypothesis | A | B | Delta | CI low | CI high | n |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for c in summary["contrasts"]:
        if c.get("status") != "ok":
            lines.append(f"| {c['label']} | {c['a']} | {c['b']} | n/a | n/a | n/a | 0 |")
            continue
        post_hoc = " (post-hoc pool)" if c.get("selected_post_hoc") else ""
        lines.append(
            f"| {c['label']}{post_hoc} | {c['a']} | {c['b']} "
            f"| {c['delta']:.4f} | {c['ci_low']:.4f} | {c['ci_high']:.4f} | {int(c['n'])} |"
        )

    lines.extend(
        [
            "",
            "## Per-cell aggregates (measured rows only)",
            "",
            "| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | Mean ms | P95 ms | n |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for cid, m in sorted(summary["per_cell"].items()):
        lines.append(
            f"| {cid} | {m['coverage_at_20']:.4f} | {m['recall_at_50']:.4f} "
            f"| {m['alpha_ndcg_at_10']:.4f} | {m['hit_at_10']:.4f} | {m['mrr_at_10']:.4f} "
            f"| {m['mean_latency_ms']:.1f} | {m['p95_latency_ms']:.1f} | {m['n_measured']} |"
        )

    if summary["invalid_cells"]:
        lines.extend(["", "## Invalid cells", ""])
        lines.extend(f"- `{e['cell_id']}`: {e['reason']}" for e in summary["invalid_cells"])
    if summary["incomplete_cells"]:
        lines.extend(["", "## Incomplete cells", ""])
        lines.extend(
            f"- `{e['cell_id']}` ({e['status']}): {e['reason']}"
            for e in summary["incomplete_cells"]
        )
    if summary["missing_cells"]:
        lines.extend(["", "## Contrasts not computable", ""])
        lines.extend(
            f"- {e['hypothesis']}: cell `{e['cell_id']}` absent or not complete"
            for e in summary["missing_cells"]
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=SCRIPT_DIR / "output" / "eval_results.json")
    parser.add_argument(
        "--output", type=Path, default=SCRIPT_DIR / "output" / "eval_results.summary.json"
    )
    parser.add_argument("--results-md", type=Path, default=SCRIPT_DIR / "output" / "results.md")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    summary = _build_summary(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_md(summary, args.results_md)
    print(f"Summary written to {args.output}")
    print(f"Results report written to {args.results_md}")


if __name__ == "__main__":
    main()
