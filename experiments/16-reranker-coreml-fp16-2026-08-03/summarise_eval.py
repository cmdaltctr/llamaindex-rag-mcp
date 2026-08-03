#!/usr/bin/env python3
"""Summarise Experiment 16 results into results.md.

Loads eval_results.json, evaluates the pass gates from protocol.md, and writes
a human-readable results.md with the comparison table and recommendation.
"""
from __future__ import annotations

import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def _fmt_ms(val: object) -> str:
    if val is None or isinstance(val, str):
        return "N/A"
    return f"{val:.1f}"


def main() -> None:
    results_path = SCRIPT_DIR / "output" / "eval_results.json"
    if not results_path.exists():
        print(f"No results at {results_path}. Run run_eval.py first.")
        return

    data = json.loads(results_path.read_text(encoding="utf-8"))
    cells = data.get("cells", [])
    by_id = {c["cell_id"]: c for c in cells}

    a = by_id.get("16A", {})
    b = by_id.get("16B", {})
    c = by_id.get("16C", {})

    # ── Pass gate evaluation ───────────────────────────────────────────
    h1_pass = b.get("loaded", False)
    h1_error = b.get("load_error")

    h2_pass = False
    h2_margin = None
    if h1_pass and a.get("p50_query_ms") and b.get("p50_query_ms"):
        h2_margin = round(a["p50_query_ms"] - b["p50_query_ms"], 2)
        h2_pass = h2_margin >= 5.0

    h3_cold_ok = True
    if h1_pass and a.get("cold_start_s") and b.get("cold_start_s"):
        h3_cold_ok = b["cold_start_s"] <= 3 * a["cold_start_s"]

    h3_rss_ok = True
    if h1_pass and a.get("peak_rss_mb") and b.get("peak_rss_mb"):
        h3_rss_ok = b["peak_rss_mb"] <= 2 * a["peak_rss_mb"]

    # ── Recommendation ─────────────────────────────────────────────────
    if not h1_pass:
        verdict = "FAIL"
        recommendation = (
            "CoreML crashed on fp16 load. Keep int8 + CPU as the swap "
            "default. No change to provider logic."
        )
    elif not h2_pass:
        verdict = "INCONCLUSIVE"
        recommendation = (
            "CoreML loads but does not beat int8 + CPU by >=5ms P50. "
            "Keep int8 + CPU. The RERANK_ONNX_PROVIDER=coreml escape "
            "hatch stays for manual opt-in."
        )
    elif not h3_cold_ok or not h3_rss_ok:
        verdict = "INCONCLUSIVE"
        recommendation = (
            "CoreML is faster but footprint is pathological. Keep "
            "int8 + CPU unless the latency margin is very large."
        )
    else:
        c_beats_a = (
            c.get("p50_query_ms") and a.get("p50_query_ms")
            and c["p50_query_ms"] < a["p50_query_ms"]
        )
        if c_beats_a:
            verdict = "PASS (fp16 win, not CoreML)"
            recommendation = (
                "fp16 precision is the win, not CoreML. Update swap "
                "design to prefer fp16 on CPU. CoreML stays off."
            )
        else:
            verdict = "PASS (CoreML win)"
            recommendation = (
                "fp16 + CoreML wins. Update swap design: fp16 becomes "
                "preferred variant on M-series, auto-select CoreML EP "
                "for fp16 variant."
            )

    # ── Build results.md ───────────────────────────────────────────────
    lines = [
        "# Experiment 16: Reranker CoreML EP + fp16 feasibility and latency",
        "",
        f"**Status**: {verdict}",
        f"**Date**: 2026-08-03",
        f"**Model**: `{data.get('model', 'Alibaba-NLP/gte-reranker-modernbert-base')}`",
        f"**Platform**: {data.get('platform', 'N/A')} | {data.get('machine', 'N/A')}",
        f"**Iterations**: {data.get('iterations', 'N/A')} warm × "
        f"{data.get('queries', 'N/A')} queries × "
        f"{data.get('docs_per_query', 'N/A')} docs",
        "",
        "---",
        "",
        "## Cell comparison",
        "",
        "| Cell | Variant | Provider | Loaded | P50 (ms) | P95 (ms) | "
        "Mean (ms) | Cold start (s) | Peak RSS (MB) |",
        "| --- | --- | --- | :---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for cell in (a, b, c):
        if not cell:
            continue
        cid = cell.get("cell_id", "?")
        variant = cell.get("variant", "?").replace("onnx/", "")
        provs = ", ".join(cell.get("actual_providers", cell.get("requested_providers", [])))
        loaded = "yes" if cell.get("loaded") else "**NO**"
        lines.append(
            f"| {cid} | {variant} | {provs} | {loaded} | "
            f"{_fmt_ms(cell.get('p50_query_ms'))} | "
            f"{_fmt_ms(cell.get('p95_query_ms'))} | "
            f"{_fmt_ms(cell.get('mean_query_ms'))} | "
            f"{cell.get('cold_start_s', 'N/A')} | "
            f"{cell.get('peak_rss_mb', 'N/A')} |"
        )

    lines.extend([
        "",
        "## Pass gates",
        "",
        "| Gate | Result | Detail |",
        "| --- | :---: | --- |",
        f"| H1 — fp16 + CoreML loads | {'PASS' if h1_pass else 'FAIL'} | "
        f"{('Clean load' if h1_pass else h1_error)} |",
        f"| H2 — P50 margin >= 5ms | {'PASS' if h2_pass else 'FAIL'} | "
        f"16A−16B = {h2_margin if h2_margin is not None else 'N/A'}ms |",
        f"| H3 — cold start <= 3x | {'PASS' if h3_cold_ok else 'FAIL'} | "
        f"16A={a.get('cold_start_s', 'N/A')}s, "
        f"16B={b.get('cold_start_s', 'N/A')}s |",
        f"| H3 — peak RSS <= 2x | {'PASS' if h3_rss_ok else 'FAIL'} | "
        f"16A={a.get('peak_rss_mb', 'N/A')}MB, "
        f"16B={b.get('peak_rss_mb', 'N/A')}MB |",
        "",
        "## Recommendation",
        "",
        recommendation,
        "",
    ])

    # ── Per-iteration detail (if available) ────────────────────────────
    if a.get("iteration_totals_ms") or b.get("iteration_totals_ms"):
        lines.extend([
            "## Per-iteration latency (ms, all queries)",
            "",
            "| Iteration | 16A | 16B | 16C |",
            "| ---: | ---: | ---: | ---: |",
        ])
        max_iters = max(
            len(a.get("iteration_totals_ms", [])),
            len(b.get("iteration_totals_ms", [])),
            len(c.get("iteration_totals_ms", [])),
        )
        for i in range(max_iters):
            row = [str(i + 1)]
            for cell in (a, b, c):
                vals = cell.get("iteration_totals_ms", [])
                row.append(str(vals[i]) if i < len(vals) else "—")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines.extend([
        "## Load errors (if any)",
        "",
    ])
    any_error = False
    for cell in (a, b, c):
        if cell.get("load_error"):
            any_error = True
            lines.append(f"- **{cell['cell_id']}**: `{cell['load_error']}`")
    if not any_error:
        lines.append("None — all cells loaded successfully.")
    lines.append("")

    results_path = SCRIPT_DIR / "results.md"
    results_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Results written to {results_path}")
    print(f"Verdict: {verdict}")


if __name__ == "__main__":
    main()
