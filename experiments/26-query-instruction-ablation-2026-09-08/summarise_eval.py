"""Experiment 26 summariser: aggregate both arms, check the frozen gates.

Metric definitions are the verbatim Experiment 22 port, shared via
``_lib.retrieval_metrics`` so every cell is scored by identical code and
the numbers stay comparable with the baseline. Do not modify them.

Repair tasks 4.2/4.3: before any gate is evaluated, every cell is
validated against the declared observation set (the 223 ground-truth
query ids and their categories) via ``_lib.checkpoint_validity``. A
well-formed subset is INCOMPLETE; duplicates, unexpected ids, category
drift, malformed rows, non-finite latencies, a ``done``/``rows`` desync
or differing id sets between arms are INVALID. Neither status produces
a verdict or promotion advice.

Outputs never overwrite the frozen historical artefacts: the summariser
writes ``eval_results.summary.json`` and ``results.md`` into an explicit
out directory (default ``output/recovery-<date>/``), leaving the
committed 2026-09-09 run untouched. Gate thresholds are read from the
frozen ``plan.json`` and never from this file; comparisons use unrounded
values and rounding happens only in formatting.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR.parent))

from _lib.checkpoint_validity import validate_cells  # noqa: E402
from _lib.retrieval_metrics import _aggregate, _metrics_for_query  # noqa: E402

EXP22_DIR = EXP_DIR.parent / "22-raw-query-qwen4b-baseline-2026-09-07"
GT_PATH = EXP22_DIR / "output/ground-truth.json"
BASELINE_CKPT = EXP22_DIR / "output/cells/hybrid__raw.json"
PLAN_PATH = EXP_DIR / "plan.json"
MANIFEST_PATH = EXP_DIR / "output/runtime_manifest.json"
CELLS = ("raw_none", "candidate_instruction")
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20260908


# ---------------------------------------------------------------------
# Experiment 26 aggregation and gate evaluation
# ---------------------------------------------------------------------
def _scored_rows(checkpoint: Path, queries: dict) -> list[dict]:
    """Attach per-query metrics to one arm's checkpoint rows."""
    state = json.loads(checkpoint.read_text(encoding="utf-8"))
    return [
        {**row, "metrics": _metrics_for_query(row["parent_ids"], queries[row["query_id"]])}
        for row in state["rows"]
    ]


def _paired(raw: list[dict], cand: list[dict], key: str, categories=None) -> list[float]:
    """Per-query candidate-minus-raw deltas over the shared query ids."""
    by_id = {r["query_id"]: r for r in raw}
    return [
        c["metrics"][key] - by_id[c["query_id"]]["metrics"][key]
        for c in cand
        if c["query_id"] in by_id and (categories is None or c["category"] in categories)
    ]


def _bootstrap_half_width(deltas: list[float]) -> float:
    """Paired bootstrap 95% half-width of the mean delta."""
    rng = random.Random(BOOTSTRAP_SEED)  # noqa: S311 - reproducible bootstrap, not crypto
    size = len(deltas)
    means = sorted(statistics.fmean(rng.choices(deltas, k=size)) for _ in range(BOOTSTRAP_N))
    lower = means[int(0.025 * BOOTSTRAP_N)]
    upper = means[int(0.975 * BOOTSTRAP_N) - 1]
    return (upper - lower) / 2


def _gates(plan: dict, raw: list[dict], cand: list[dict], agg_cand: dict) -> dict:
    """Evaluate every frozen gate against the measured arms."""
    by_kind = {g["kind"]: g for g in plan["validity_gates"]}
    quality, regression, latency = by_kind["quality"], by_kind["regression"], by_kind["latency"]

    deltas = _paired(raw, cand, "recall_at_5")
    lift = statistics.fmean(deltas)
    ident_r10 = agg_cand.get("identifier-heavy", {}).get("recall_at_10", 0.0)
    p95 = agg_cand["all"]["p95_latency_ms"]

    return {
        "quality_paired_r5_lift": {
            "pass": lift >= quality["threshold"],
            "measured": round(lift, 6),
            "threshold": quality["threshold"],
            "comparator": quality["comparator"],
            "paired_bootstrap_95_half_width": round(_bootstrap_half_width(deltas), 6),
            "n": len(deltas),
        },
        "regression_identifier_r10": {
            "pass": ident_r10 >= regression["threshold"],
            "measured": round(ident_r10, 6),
            "threshold": regression["threshold"],
            "comparator": regression["comparator"],
            "n": agg_cand.get("identifier-heavy", {}).get("n", 0),
        },
        "latency_p95_ms": {
            "pass": p95 <= latency["threshold"],
            "measured": p95,
            "threshold": latency["threshold"],
            "comparator": latency["comparator"],
        },
    }


def _drift_check(raw: list[dict], queries: dict) -> dict:
    """Compare this run's raw arm with Experiment 22's published raw arm."""
    exp22 = _scored_rows(BASELINE_CKPT, queries)
    local = _aggregate(raw)["all"]
    published = _aggregate(exp22)["all"]
    return {
        "exp22_recall_at_5": published["recall_at_5"],
        "exp26_raw_recall_at_5": local["recall_at_5"],
        "delta": round(local["recall_at_5"] - published["recall_at_5"], 6),
        "note": "same index and queries; a non-zero delta between dates is "
        "consistent with provider-side or pipeline variance between runs and "
        "does not by itself identify a cause. An equal aggregate also does "
        "not show rank-level stability; per-query rankings may differ.",
    }


def _rows_table(agg: dict, cats: tuple[str, ...]) -> list[str]:
    cols = ("recall_at_1", "recall_at_3", "recall_at_5", "recall_at_10", "mrr_at_10")
    lines = ["| Category | n | R@1 | R@3 | R@5 | R@10 | MRR@10 |", "| --- | ---: |" + " ---: |" * 5]
    for cat in cats:
        if cat not in agg:
            continue
        row = agg[cat]
        cells = " | ".join(f"{row[c] * 100:.1f}%" for c in cols)
        lines.append(f"| {cat} | {row['n']} | {cells} |")
    return lines


def _validation_lines(summary: dict) -> list[str]:
    """Render the validity block for a non-complete summary."""
    lines = ["## Measurement validity", ""]
    for cell, result in summary["validation"]["cells"].items():
        lines.append(
            f"- `{cell}`: {result['status'].upper()} — {result['n_rows']} of "
            f"{result['expected_n']} expected queries."
        )
        lines.extend(f"  - {reason}" for reason in result["reasons"])
    lines.extend(f"- Pairing: {reason}" for reason in summary["validation"]["pairing_reasons"])
    lines += [
        "",
        "No gate is evaluated and no verdict or recommendation is issued",
        "from this state. INCOMPLETE: the declared query set is not fully",
        "measured here. INVALID: at least one cell is malformed, duplicated,",
        "mislabelled or covers a different query set.",
        "",
    ]
    return lines


def _write_results_md(summary: dict, plan: dict) -> None:
    """Render results.md from the computed summary into the out directory."""
    out_path = Path(summary["out_dir"]) / "results.md"
    header = [
        "# Experiment 26 Results: Query-instruction ablation (task 5.3)",
        "",
        "**ID**: `26-query-instruction-ablation-2026-09-08`  ",
        f"**Report generated**: {summary['generated_utc']}  ",
        f"**Status**: {summary['status'].upper()}"
        + (f" (verdict {summary['verdict']})" if summary.get("verdict") else "")
        + "  ",
        f"**Cells source**: `{summary['cells_source']}`  ",
        "**Raw data**: the checkpoint files named in `cell_sources` (read-only)",
        "",
        "---",
        "",
    ]
    if summary["status"] != "complete":
        body = [
            "## Summary",
            "",
            summary["headline"],
            "",
            *_validation_lines(summary),
            "## Reproduction",
            "",
            "```bash",
            "uv run python experiments/26-query-instruction-ablation-2026-09-08/summarise_eval.py \\",
            f"  --cells-dir <cells> --out-dir {summary['out_dir']}",
            "```",
            "",
            "This regenerated report never overwrites the frozen historical",
            "artefacts (`output/cells/`, `output/eval_results.summary.json`,",
            "`results.md` at the experiment root).",
            "",
        ]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(header + body), encoding="utf-8")
        return

    gates = summary["gates"]
    cats = ("all", "identifier-heavy", "semantic", "continuity")
    raw_agg = summary["metrics_by_cell"]["raw_none"]
    cand_agg = summary["metrics_by_cell"]["candidate_instruction"]
    q, r, lat = (
        gates["quality_paired_r5_lift"],
        gates["regression_identifier_r10"],
        gates["latency_p95_ms"],
    )
    mark = {True: "✅ PASS", False: "❌ FAIL"}
    lines = header + [
        "## TL;DR / Decision",
        "",
        summary["headline"],
        "",
        "## Frozen gate checks",
        "",
        "| Gate | Rule | Measured | Verdict |",
        "| --- | --- | --- | --- |",
        f"| Quality | paired mean R@5 lift ≥ {q['threshold']:+.4f} | "
        f"{q['measured']:+.4f} (95% half-width ±{q['paired_bootstrap_95_half_width']:.4f}, "
        f"n={q['n']}) | {mark[q['pass']]} |",
        f"| Regression | identifier-heavy R@10 ≥ {r['threshold']} | "
        f"{r['measured']:.4f} (n={r['n']}) | {mark[r['pass']]} |",
        f"| Latency | query p95 ≤ {lat['threshold']} ms | {lat['measured']:,.0f} ms | "
        f"{mark[lat['pass']]} |",
        "",
        "Thresholds are read from the frozen [`plan.json`](./plan.json); no",
        "threshold lives in the summariser. The gates were frozen on",
        f"{plan['gate_freeze']['frozen_date']} and are unchanged.",
        "",
        "## Raw arm (`raw_none`)",
        "",
        *_rows_table(raw_agg, cats),
        "",
        "## Instructed arm (`candidate_instruction`)",
        "",
        *_rows_table(cand_agg, cats),
        "",
        "## Candidate instruction",
        "",
        "```text",
        summary["runtime_manifest"]["embedding"]["candidate_instruction"],
        "```",
        "",
        "## Latency",
        "",
        "| Arm | Mean | P95 |",
        "| --- | ---: | ---: |",
        f"| raw_none | {raw_agg['all']['mean_latency_ms']:,.0f} ms | "
        f"{raw_agg['all']['p95_latency_ms']:,.0f} ms |",
        f"| candidate_instruction | {cand_agg['all']['mean_latency_ms']:,.0f} ms | "
        f"{cand_agg['all']['p95_latency_ms']:,.0f} ms |",
        "",
        summary["execution"]["periods_text"],
        "Latency is cloud-inclusive. Absolute latency comparisons across",
        "different dates are inconclusive: provider-side variance between",
        "days is not measured separately here. The first query of a run",
        "pays the one-off BM25 index build; that cost lands on whichever",
        "arm was scheduled first (`arm_position` 1).",
        "",
        "## Drift cross-check against Experiment 22",
        "",
        f"- Experiment 22 published R@5 (hybrid, raw): {summary['drift']['exp22_recall_at_5']:.6f}",
        f"- This run's raw arm R@5: {summary['drift']['exp26_raw_recall_at_5']:.6f}",
        f"- Delta: {summary['drift']['delta']:+.6f}",
        "",
        "Same index, same 223 queries. An equal aggregate does not show",
        "rank-level stability: per-query rankings can differ while the mean",
        "matches. The gate is evaluated against this run's own raw arm,",
        "which is paired query by query with the instructed arm;",
        "Experiment 22's number is a drift check only.",
        "",
        "## Monitored, not gated",
        "",
        f"- Continuity R@10 (n={cand_agg.get('continuity', {}).get('n', 0)}): raw "
        f"{raw_agg.get('continuity', {}).get('recall_at_10', 0):.4f} → candidate "
        f"{cand_agg.get('continuity', {}).get('recall_at_10', 0):.4f}. The bootstrap",
        "  95% half-width at n=20 is ±0.15, so no hard gate could be meaningful.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "uv run python experiments/26-query-instruction-ablation-2026-09-08/summarise_eval.py \\",
        f"  --cells-dir {summary['cells_source']} --out-dir {summary['out_dir']}",
        "```",
        "",
        "No index is built or written: both arms query the preserved",
        "Experiment 22 index read-only. This regenerated report never",
        "overwrites the frozen historical artefacts.",
        "",
    ]
    # Hand-written interpretation lives in its own file so regenerating
    # the tables never discards it.
    discussion = EXP_DIR / "discussion.md"
    if discussion.exists():
        lines.append(discussion.read_text(encoding="utf-8"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def summarise_from(cells_dir: Path, out_dir: Path) -> dict:
    """Validate, aggregate and gate the cells; write only into ``out_dir``.

    The declared observation set is the ground truth's query ids and
    categories. Gates and promotion wording are produced only when every
    cell is complete and the arms share identical query membership.
    """
    queries_raw = json.loads(GT_PATH.read_text(encoding="utf-8"))["queries"]
    queries = {q["query_id"]: q for q in queries_raw}
    expected = {q["query_id"]: q["category"] for q in queries_raw}
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    states = {
        cell: json.loads((cells_dir / f"{cell}.json").read_text(encoding="utf-8")) for cell in CELLS
    }
    validation = validate_cells(states, expected)
    print(f"[summarise] validity: {validation['status']}", flush=True)

    session_path = cells_dir.parent / "session.json"
    historical = not session_path.exists()
    summary: dict = {
        "experiment": EXP_DIR.name,
        "generated_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "status": validation["status"],
        "verdict": None,
        "validation": validation,
        "provenance": {
            "cells_source": str(cells_dir),
            "historical": historical,
            "limits": [
                "historical checkpoints carry no run identity or session "
                "recording; execution periods and code provenance at "
                "measurement time are not available"
            ]
            if historical
            else [],
        },
        "cells_source": str(cells_dir),
        "out_dir": str(out_dir),
        "cell_sources": {cell: str(cells_dir / f"{cell}.json") for cell in CELLS},
    }
    if validation["status"] != "complete":
        worst = "INVALID" if validation["status"] == "invalid" else "INCOMPLETE"
        summary["headline"] = (
            f"- **No verdict.** Measurement set is {worst}: "
            + "; ".join(
                f"{cell} {result['status']} ({result['n_rows']}/{result['expected_n']})"
                for cell, result in validation["cells"].items()
            )
            + ". Gates are not evaluated; no recommendation follows from this state."
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp = (out_dir / "eval_results.summary.json").with_suffix(".json.tmp")
        tmp.write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
        tmp.replace(out_dir / "eval_results.summary.json")
        _write_results_md(summary, plan)
        print(f"[summarise] status={validation['status']} → {out_dir}", flush=True)
        return summary

    session = json.loads(session_path.read_text(encoding="utf-8")) if not historical else None

    scored = {
        cell: [
            {**row, "metrics": _metrics_for_query(row["parent_ids"], queries[row["query_id"]])}
            for row in states[cell]["rows"]
        ]
        for cell in CELLS
    }
    counts = {cell: len(rows) for cell, rows in scored.items()}
    print(f"[summarise] {counts['raw_none']} queries per arm", flush=True)

    aggregates = {cell: _aggregate(rows) for cell, rows in scored.items()}
    gates = _gates(
        plan,
        scored["raw_none"],
        scored["candidate_instruction"],
        aggregates["candidate_instruction"],
    )
    verdict = "PASS" if all(g["pass"] for g in gates.values()) else "FAIL"
    failed = [name for name, gate in gates.items() if not gate["pass"]]

    lift = gates["quality_paired_r5_lift"]["measured"]
    if verdict == "PASS":
        headline = (
            f"- All three frozen gates pass. The candidate instruction lifts paired\n"
            f"  mean R@5 by {lift:+.4f} without breaching the identifier-heavy or\n"
            f"  latency guards.\n"
            f"- Eligible for promotion of `EMBEDDING__QUERY_INSTRUCTION` under task 5.5."
        )
    else:
        headline = (
            f"- **Negative result.** Failed gates: {', '.join(failed)}.\n"
            f"- Paired mean R@5 lift is {lift:+.4f} against a frozen requirement of\n"
            f"  {gates['quality_paired_r5_lift']['threshold']:+.4f}.\n"
            f"- Per task 5.5 the packaged default for `EMBEDDING__QUERY_INSTRUCTION`\n"
            f"  stays empty. The instruction text is not tuned to chase the gate."
        )

    summary |= {
        "verdict": verdict,
        "failed_gates": failed,
        "headline": headline,
        "gates": gates,
        "metrics_by_cell": aggregates,
        "drift": _drift_check(scored["raw_none"], queries),
        "execution": {"session": session, "periods_text": _execution_periods_text(session)},
        "runtime_manifest": json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "eval_results.summary.json"
    tmp = out_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(out_json)
    _write_results_md(summary, plan)
    print(f"[summarise] verdict={verdict} → {out_json}", flush=True)
    return summary


def _execution_periods_text(session: dict | None) -> str:
    """Report wording for execution periods (repair task 4.5)."""
    if session is None:
        return (
            "Execution periods were not recorded for this run (historical "
            "checkpoint; provenance limit). Both arms were interleaved per "
            "query with alternating arm order, so arm-order bias is "
            "controlled, but a single uninterrupted network period cannot "
            "be claimed from the data."
        )
    periods = session.get("periods", [])
    if len(periods) <= 1:
        return (
            f"Session {session.get('session_id', '?')}: measurements were taken "
            "in a single recorded execution period; both arms were interleaved "
            "per query with alternating arm order."
        )
    return (
        f"Session {session.get('session_id', '?')}: measurements span "
        f"{len(periods)} mixed execution periods with "
        f"{session.get('interruptions', 0)} recorded interruption(s); both arms "
        "were interleaved per query, but a common network epoch across periods "
        "is not claimed."
    )


def main() -> None:
    """Summarise validated cells into an explicit out directory."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cells-dir",
        type=Path,
        default=EXP_DIR / "output/cells",
        help="directory holding <cell>.json checkpoints (default: historical)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=EXP_DIR / "output/recovery-2026-09-10",
        help="distinct report destination; frozen historical outputs are never written",
    )
    args = parser.parse_args()
    summarise_from(args.cells_dir, args.out_dir)


if __name__ == "__main__":
    main()
