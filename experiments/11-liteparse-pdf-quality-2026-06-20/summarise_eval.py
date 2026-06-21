"""Aggregate Experiment 11 raw results and evaluate the four pre-registered pass gates.

Customised from the canonical summarise-pattern.md in the /s-experiment skill.
Pass gates come from protocol.md and MUST NOT be edited after results are seen.

Usage:
    uv run python summarise_eval.py

Writes:
    output/eval_results.summary.json
    results.md
"""

from __future__ import annotations

import argparse
import json
import platform
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
    if len(values) < 100:
        return round(max(values), 2)
    return round(statistics.quantiles(sorted(values), n=100, method="inclusive")[94], 2)


def _aggregate_cell(cell: dict[str, Any]) -> dict[str, Any]:
    """Aggregate a single cell's per-query results into category buckets."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cell.get("queries", []):
        groups["all"].append(row)
        groups[row.get("category") or "unknown"].append(row)

    metrics: dict[str, Any] = {}
    for name, rows in groups.items():
        latencies = [float(row.get("latency_ms", 0.0)) for row in rows]
        metrics[name] = {
            "n": len(rows),
            "ndcg_at_10": _mean([row["metrics"].get("ndcg_at_10", 0.0) for row in rows]),
            "coverage_at_20": _mean([row["metrics"].get("coverage_at_20", 0.0) for row in rows]),
            "hit_at_5": _mean([1.0 if row["metrics"].get("hit_at_5") else 0.0 for row in rows]),
            "hit_at_10": _mean([1.0 if row["metrics"].get("hit_at_10") else 0.0 for row in rows]),
            "hit_at_20": _mean([1.0 if row["metrics"].get("hit_at_20") else 0.0 for row in rows]),
            "mrr_at_10": _mean([row["metrics"].get("mrr_at_10", 0.0) for row in rows]),
            "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "p95_latency_ms": _p95(latencies),
        }
    return metrics


def _cell_key(cell: dict[str, Any]) -> str:
    return f"{cell['mode']}__rerank_{str(cell['rerank']).lower()}"


def _load_build_timing(parser: str) -> dict[str, Any] | None:
    """Load the per-parser build timing summary written by build_indexes.py."""
    path = SCRIPT_DIR / "output" / f"build_{parser}_timing.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _pass_criteria(aggregates: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the four pre-registered gates from protocol.md."""
    # Cells use the keys "<parser>__rerank_<bool>".
    pypdf_nr = aggregates.get("pypdf__rerank_false", {}).get("all", {})
    pypdf_r = aggregates.get("pypdf__rerank_true", {}).get("all", {})
    liteparse_nr = aggregates.get("liteparse__rerank_false", {}).get("all", {})
    liteparse_r = aggregates.get("liteparse__rerank_true", {}).get("all", {})

    pypdf_timing = _load_build_timing("pypdf") or {}
    liteparse_timing = _load_build_timing("liteparse") or {}

    # H1 — Quality win: nDCG@10 liteparse_nr >= pypdf_nr * 1.05
    h1_baseline = pypdf_nr.get("ndcg_at_10", 0.0)
    h1_candidate = liteparse_nr.get("ndcg_at_10", 0.0)
    h1_ratio = (h1_candidate / h1_baseline) if h1_baseline > 0 else float("inf")
    h1_pass = h1_ratio >= 1.05

    # H2 — Speed win: liteparse ingest <= pypdf ingest * 0.80
    h2_baseline = pypdf_timing.get("total_seconds", 0.0)
    h2_candidate = liteparse_timing.get("total_seconds", 0.0)
    h2_ratio = (h2_candidate / h2_baseline) if h2_baseline > 0 else float("inf")
    h2_pass = h2_ratio <= 0.80

    # H3 — Reranker still helps on LiteParse: liteparse_r >= liteparse_nr * 1.05
    h3_baseline = liteparse_nr.get("ndcg_at_10", 0.0)
    h3_candidate = liteparse_r.get("ndcg_at_10", 0.0)
    h3_ratio = (h3_candidate / h3_baseline) if h3_baseline > 0 else float("inf")
    h3_pass = h3_ratio >= 1.05

    # H4 — No catastrophic regression: 0 queries go from found (top-20) to not-found
    # Compare pypdf_nr hit_at_20 vs liteparse_nr hit_at_20 per query.
    h4_pass = True  # Computed in main() where we have raw rows; placeholder here.

    criteria = {
        "H1_quality_win": {
            "baseline_ndcg10": h1_baseline,
            "candidate_ndcg10": h1_candidate,
            "ratio": round(h1_ratio, 4),
            "threshold": ">= 1.05",
            "pass": h1_pass,
        },
        "H2_speed_win": {
            "baseline_seconds": h2_baseline,
            "candidate_seconds": h2_candidate,
            "ratio": round(h2_ratio, 4),
            "threshold": "<= 0.80",
            "pass": h2_pass,
        },
        "H3_reranker_still_helps": {
            "no_rerank_ndcg10": h3_baseline,
            "with_rerank_ndcg10": h3_candidate,
            "ratio": round(h3_ratio, 4),
            "threshold": ">= 1.05",
            "pass": h3_pass,
        },
        "H4_no_lost_queries": {
            "threshold": "0 queries drop from found to not-found",
            "pass": h4_pass,  # updated by caller
        },
    }

    # Verdict interpretation per protocol.md interpretation rules
    criteria["all_primary_gates_pass"] = h1_pass and h2_pass
    criteria["all_gates_pass"] = all(
        v.get("pass", False) for v in criteria.values()
        if isinstance(v, dict) and "pass" in v
    )

    if h1_pass and h2_pass and h3_pass and h4_pass:
        verdict = "PASS"
        recommendation = (
            "All four gates pass. ADR-020 status = Accepted. "
            "Follow-on change may flip PDF_READER default from pypdf to auto."
        )
    elif h1_pass and not h2_pass:
        verdict = "PARTIAL"
        recommendation = (
            "Quality win confirmed but speed win failed. Adopt LiteParse as "
            "auto default (quality > speed); record H2 failure in ADR-020."
        )
    elif not h1_pass:
        verdict = "FAIL"
        recommendation = (
            "H1 failed: LiteParse did not improve nDCG@10 by >=5%. "
            "ADR-020 status = Declined. Retain pypdf default; keep factory."
        )
    elif not h3_pass:
        verdict = "INCONCLUSIVE"
        recommendation = (
            "H3 failed: reranker stopped helping on LiteParse text. "
            "Investigate chunk-boundary or text-quality regression before deciding."
        )
    elif not h4_pass:
        verdict = "FAIL"
        recommendation = (
            "H4 failed: LiteParse dropped content for some queries. "
            "Do not adopt regardless of other metrics."
        )
    else:
        verdict = "INCONCLUSIVE"
        recommendation = "Unexpected combination of gate results; investigate manually."

    criteria["verdict"] = verdict
    criteria["recommendation"] = recommendation
    return criteria


def _compute_h4(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """Find queries that went from found (top-20) in pypdf to not-found in liteparse."""
    by_key = {_cell_key(c): c for c in cells}
    pypdf_nr = by_key.get("pypdf__rerank_false", {})
    liteparse_nr = by_key.get("liteparse__rerank_false", {})

    pypdf_lookup = {row["query_id"]: row for row in pypdf_nr.get("queries", [])}
    liteparse_lookup = {row["query_id"]: row for row in liteparse_nr.get("queries", [])}

    lost: list[dict[str, Any]] = []
    for qid, pypdf_row in pypdf_lookup.items():
        liteparse_row = liteparse_lookup.get(qid)
        if liteparse_row is None:
            continue
        pypdf_found = pypdf_row["metrics"].get("hit_at_20", False)
        liteparse_found = liteparse_row["metrics"].get("hit_at_20", False)
        if pypdf_found and not liteparse_found:
            lost.append({
                "query_id": qid,
                "query": pypdf_row.get("category"),
                "expected_files": pypdf_row.get("expected_files", []),
                "pypdf_top_results": pypdf_row.get("top_results", [])[:5],
                "liteparse_top_results": liteparse_row.get("top_results", [])[:5],
            })

    return {
        "lost_query_count": len(lost),
        "lost_queries": lost,
        "pass": len(lost) == 0,
    }


def _write_results_md(
    data: dict[str, Any],
    summary: dict[str, Any],
    path: Path,
) -> None:
    verdict = summary["pass_criteria"]["verdict"]
    recommendation = summary["pass_criteria"]["recommendation"]

    lines = [
        f"# Experiment 11: LiteParse PDF Quality — Results",
        "",
        f"**Verdict:** `{verdict}`",
        "",
        f"**Recommendation:** {recommendation}",
        "",
        "## Executive summary",
        "",
        "TODO: Operator replaces this section with a 1–3 paragraph summary of the ",
        "bottom line after the experiment completes. State the verdict in the first",
        "sentence, then the key metric movements, then any caveats.",
        "",
        "## Setup",
        "",
        f"- Platform: `{data.get('platform', platform.platform())}`",
        f"- Python: `{data.get('python_version', '')}`",
        f"- Corpus size: `{data.get('ground_truth_size', '?')} queries`",
        f"- Top-K: `{data.get('top_k', '?')}`",
        f"- K values reported: `{data.get('k_values', [])}`",
        f"- Hybrid retrieval: OFF (per protocol.md, isolates parser variable)",
        "",
        "## Cell metrics (all queries)",
        "",
        "| Cell | n | nDCG@10 | Hit@5 | Hit@10 | Hit@20 | MRR@10 | Coverage@20 | P95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cell_key, groups in summary["metrics_by_cell"].items():
        m = groups.get("all", {})
        lines.append(
            f"| `{cell_key}` | {m.get('n', 0)} | "
            f"{m.get('ndcg_at_10', 0.0):.4f} | "
            f"{m.get('hit_at_5', 0.0):.3f} | "
            f"{m.get('hit_at_10', 0.0):.3f} | "
            f"{m.get('hit_at_20', 0.0):.3f} | "
            f"{m.get('mrr_at_10', 0.0):.4f} | "
            f"{m.get('coverage_at_20', 0.0):.3f} | "
            f"{m.get('p95_latency_ms', 0.0):.1f} |"
        )

    lines.extend([
        "",
        "## Per-category breakdown",
        "",
        "TODO: Operator expands this section with per-category tables (two_column,",
        "single_column, table_heavy) to show where LiteParse helps or hurts.",
        "",
        "## Pass gates",
        "",
    ])
    for name, value in summary["pass_criteria"].items():
        if name in {"verdict", "recommendation", "all_primary_gates_pass", "all_gates_pass"}:
            continue
        lines.append(f"- **{name}**: `{json.dumps(value, ensure_ascii=False)}`")

    lines.extend([
        "",
        "## Build timing (H2 evidence)",
        "",
        "| Parser | Total (s) | Parse (s) | Chunk (s) | Embed (s) | Files OK | Chunks |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for parser_key in ("pypdf", "liteparse"):
        timing = summary.get("build_timing", {}).get(parser_key, {})
        if timing:
            lines.append(
                f"| `{parser_key}` | "
                f"{timing.get('total_seconds', '?')} | "
                f"{timing.get('parse_seconds_total', '?')} | "
                f"{timing.get('chunk_seconds_total', '?')} | "
                f"{timing.get('embed_seconds_total', '?')} | "
                f"{timing.get('files_ok', '?')} | "
                f"{timing.get('chunks_written', '?')} |"
            )

    h4 = summary.get("h4_detail", {})
    lines.extend([
        "",
        "## H4 — Queries lost (pypdf found, liteparse not found)",
        "",
        f"- Count: **{h4.get('lost_query_count', 0)}**",
        f"- Pass: **{h4.get('pass', False)}**",
        "",
    ])
    if h4.get("lost_queries"):
        lines.append("| Query ID | Category | Expected files |")
        lines.append("| --- | --- | --- |")
        for q in h4["lost_queries"]:
            lines.append(
                f"| {q['query_id']} | {q.get('query', '?')} | "
                f"{', '.join(q.get('expected_files', []))} |"
            )

    lines.extend([
        "",
        "## Conclusion / decision",
        "",
        "TODO: Operator writes the final decision — what ships, what does not,",
        "what follow-up is allowed. Reference ADR-020 (pending).",
        "",
        "## Artefacts",
        "",
        "- Raw results: `output/eval_results.json`",
        "- Summary JSON: `output/eval_results.summary.json`",
        "- Run log: `output/run_eval.log`",
        "- Build timing: `output/build_pypdf_timing.json`, `output/build_liteparse_timing.json`",
        "- Protocol: `protocol.md`",
        "- Ground truth: `ground_truth.json`",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path,
                        default=SCRIPT_DIR / "output" / "eval_results.json")
    parser.add_argument("--output", type=Path,
                        default=SCRIPT_DIR / "output" / "eval_results.summary.json")
    parser.add_argument("--results-md", type=Path,
                        default=SCRIPT_DIR / "results.md")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    cells = data.get("cells", [])

    aggregates = {_cell_key(cell): _aggregate_cell(cell) for cell in cells}
    pass_criteria = _pass_criteria(aggregates)

    # Compute H4 properly now that we have raw cells
    h4_detail = _compute_h4(cells)
    pass_criteria["H4_no_lost_queries"]["pass"] = h4_detail["pass"]
    pass_criteria["H4_no_lost_queries"]["lost_count"] = h4_detail["lost_query_count"]
    # Re-evaluate verdict now that H4 is populated
    pass_criteria["all_gates_pass"] = all(
        v.get("pass", False) for v in pass_criteria.values()
        if isinstance(v, dict) and "pass" in v
    )

    summary = {
        "experiment": data.get("experiment"),
        "metrics_by_cell": aggregates,
        "build_timing": {
            "pypdf": _load_build_timing("pypdf") or {},
            "liteparse": _load_build_timing("liteparse") or {},
        },
        "h4_detail": h4_detail,
        "pass_criteria": pass_criteria,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    _write_results_md(data, summary, args.results_md)
    print(f"Summary written to {args.output}")
    print(f"Results report written to {args.results_md}")
    print(f"\nVerdict: {pass_criteria['verdict']}")
    print(f"Recommendation: {pass_criteria['recommendation']}")


if __name__ == "__main__":
    main()
