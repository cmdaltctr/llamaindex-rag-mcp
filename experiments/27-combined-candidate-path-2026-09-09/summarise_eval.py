"""Experiment 27 summariser: assemble the 2x2, check the frozen gates.

Metric definitions are the verbatim Experiment 22 port, shared via
``_lib.retrieval_metrics`` so every cell of the 2x2 is scored by
identical code. Do not modify them. Two cells are measured by
``run_eval.py`` against the preserved Experiment 25 model-token index;
the other two are LOADED from committed checkpoints and re-aggregated,
never re-executed (``baseline_production`` → Experiment 22
``hybrid__raw``; ``instruction_only`` → Experiment 26
``candidate_instruction``).

Repair tasks 4.2/4.3: before any gate is evaluated, ALL FOUR cells are
validated against the declared observation set (the 223 ground-truth
query ids and their categories) via ``_lib.checkpoint_validity``,
including the loaded cells. A well-formed subset is INCOMPLETE;
duplicates, unexpected ids, category drift, malformed rows, non-finite
latencies, a ``done``/``rows`` desync or differing id sets between cells
are INVALID. Neither status produces a verdict or a recommendation.

Outputs never overwrite the frozen historical artefacts: everything is
written into an explicit out directory (default ``output/recovery-<date>/``),
leaving the committed 2026-09-09 run untouched. Gate thresholds are read
from the frozen ``plan.json`` and never from this file; all three gates
are evaluated on ``combined_candidate`` against the production baseline,
exactly as the plan states. The interaction term and the query token
cost are computed and reported but never gated; the plan records why.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR))
sys.path.insert(0, str(EXP_DIR.parent))

from _lib.checkpoint_validity import validate_cells  # noqa: E402
from _lib.retrieval_metrics import _aggregate, _metrics_for_query  # noqa: E402

# Experiment-local assembly diagnostics (gates, interaction, cost, drift,
# grid). The script directory is on sys.path both when run as a script
# and under runpy.run_path, so a plain import is safe here.
from assembly import _drift, _gates, _grid_table, _interaction, _query_token_cost  # noqa: E402

EXP22_DIR = EXP_DIR.parent / "22-raw-query-qwen4b-baseline-2026-09-07"
EXP26_DIR = EXP_DIR.parent / "26-query-instruction-ablation-2026-09-08"
GT_PATH = EXP22_DIR / "output/ground-truth.json"
PLAN_PATH = EXP_DIR / "plan.json"
MANIFEST_PATH = EXP_DIR / "output/runtime_manifest.json"

#: The four cells of the 2x2 and where each one's rows come from.
CELL_SOURCES = {
    "baseline_production": EXP22_DIR / "output/cells/hybrid__raw.json",
    "instruction_only": EXP26_DIR / "output/cells/candidate_instruction.json",
    "chunking_only_raw": EXP_DIR / "output/cells/chunking_only_raw.json",
    "combined_candidate": EXP_DIR / "output/cells/combined_candidate.json",
}
MEASURED_HERE = ("chunking_only_raw", "combined_candidate")


# ---------------------------------------------------------------------
# Experiment 27 report rendering and orchestration
# ---------------------------------------------------------------------
def _write_results_md(summary: dict, plan: dict) -> None:
    """Render results.md from the computed summary into the out directory."""
    from _lib.checkpoint_validity import validity_markdown_lines

    out_path = Path(summary["out_dir"]) / "results.md"
    header = [
        "# Experiment 27 Results: Combined candidate path (task 5.4)",
        "",
        "**ID**: `27-combined-candidate-path-2026-09-09`  ",
        f"**Report generated**: {summary['generated_utc']}  ",
        f"**Status**: {summary['status'].upper()}"
        + (f" (verdict {summary['verdict']})" if summary.get("verdict") else "")
        + "  ",
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
            *validity_markdown_lines(summary),
            "## Reproduction",
            "",
            "```bash",
            "uv run python experiments/27-combined-candidate-path-2026-09-09/summarise_eval.py \\",
            f"  --out-dir {summary['out_dir']}",
            "```",
            "",
            "This regenerated report never overwrites the frozen historical",
            "artefacts of experiments 22, 25, 26 or 27.",
            "",
        ]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(header + body), encoding="utf-8")
        return

    gates = summary["gates"]
    mark = {True: "✅ PASS", False: "❌ FAIL"}
    q, r, lat = (
        gates["quality_recall_at_5"],
        gates["regression_identifier_r10"],
        gates["latency_p95_ms"],
    )
    inter = summary["interaction"]
    cost = summary["query_token_cost"]
    agg = summary["metrics_by_cell"]
    cost_lines = (
        [
            f"- Mean raw query: {cost['mean_raw_tokens']} tokens.",
            f"- Mean instructed query: {cost['mean_instructed_tokens']} tokens "
            f"({cost['ratio']:.2f}x, +{cost['added_tokens_per_query']} tokens).",
            "- Counted offline with the pinned tokenizer; no API call.",
        ]
        if cost.get("available")
        else [f"- Not available: {cost.get('reason', 'tokenizer not cached')}."]
    )
    drift = summary["drift"]
    drift_lines = (
        [
            f"- Experiment 25 published R@5 ({drift['exp25_cell']}): "
            f"{drift['exp25_recall_at_5']:.6f}",
            f"- This run's `chunking_only_raw` R@5: {drift['exp27_chunking_only_recall_at_5']:.6f}",
            f"- Delta: {drift['delta']:+.6f}",
        ]
        if drift.get("available")
        else [f"- Not available: {drift.get('reason', 'exp25 summary unreadable')}."]
    )
    lines = header + [
        "## TL;DR / Decision",
        "",
        summary["headline"],
        "",
        "## Scope",
        "",
        "The FreshStack corpus contains no PDFs, so OCR routing is **not**",
        "exercised here. Its evidence is experiment 24, on a disjoint corpus",
        "of five held-out PDFs. This is the combined *retrieval* path:",
        "model-token chunking plus the candidate query instruction.",
        "",
        "## Frozen gate checks (on `combined_candidate`)",
        "",
        "| Gate | Rule | Measured | Verdict |",
        "| --- | --- | --- | --- |",
        f"| Quality | mean R@5 ≥ {q['threshold']} | {q['measured']:.6f} (n={q['n']}) | "
        f"{mark[q['pass']]} |",
        f"| Regression | identifier-heavy R@10 ≥ {r['threshold']} | {r['measured']:.6f} "
        f"(n={r['n']}) | {mark[r['pass']]} |",
        f"| Latency | query p95 ≤ {lat['threshold']} ms | {lat['measured']:,.0f} ms | "
        f"{mark[lat['pass']]} |",
        "",
        "Thresholds are read from the frozen [`plan.json`](./plan.json), frozen",
        f"{plan['gate_freeze']['frozen_date']} and unchanged. Every value is carried",
        "over from the earlier frozen plans rather than re-derived.",
        "",
        "## The 2x2",
        "",
        *_grid_table(agg),
        "",
        "`baseline_production` and `instruction_only` are loaded from their",
        "committed checkpoints and re-aggregated with identical metric code;",
        "`chunking_only_raw` and `combined_candidate` were measured in this",
        "experiment, interleaved in one process against the preserved",
        "experiment 25 index. Absolute latency is not comparable across the",
        "measurement dates shown in the table.",
        "",
        "## Interaction (monitored, not gated)",
        "",
        f"- Chunking alone: {inter['chunking_effect']:+.4f} R@5",
        f"- Instruction alone: {inter['instruction_effect']:+.4f} R@5",
        f"- Additive prediction: {inter['additive_prediction']:+.4f} R@5",
        f"- Combined, measured: {inter['combined_effect']:+.4f} R@5",
        f"- **Interaction term: {inter['interaction']:+.4f} R@5**",
        "",
        inter["note"],
        "",
        "## Cost (task 5.4 record)",
        "",
        "Index build cost is experiment 25's verified 0.974906 request-token",
        "ratio; the index is reused unchanged and not rebuilt. Query cost:",
        "",
        *cost_lines,
        "",
        "## Drift cross-check against experiment 25",
        "",
        *drift_lines,
        "",
        "## Interpretation",
        "",
        "A passing combined run does not promote the query instruction.",
        "Only experiment 26's own frozen gates can do that (task 5.5).",
        "",
        "## Reproduction",
        "",
        "```bash",
        "uv run python experiments/27-combined-candidate-path-2026-09-09/summarise_eval.py \\",
        f"  --out-dir {summary['out_dir']}",
        "```",
        "",
        "No index is built or written: both measured arms query the preserved",
        "experiment 25 index read-only. This regenerated report never",
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


def summarise_from(cells_dir: Path | None, out_dir: Path) -> dict:
    """Validate, assemble and gate the 2x2; write only into ``out_dir``.

    ``cells_dir`` (optional) overrides the two locally measured cells, as
    with a run directory's ``cells/`` subtree; the loaded reference cells
    always come from ``CELL_SOURCES``. All four cells are validated
    against the declared observation set before any gate is evaluated.
    """
    queries_raw = json.loads(GT_PATH.read_text(encoding="utf-8"))["queries"]
    queries = {q["query_id"]: q for q in queries_raw}
    expected = {q["query_id"]: q["category"] for q in queries_raw}
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    sources = dict(CELL_SOURCES)
    if cells_dir is not None:
        for cell in MEASURED_HERE:
            candidate = cells_dir / f"{cell}.json"
            if candidate.exists():
                sources[cell] = candidate
    states = {cell: json.loads(path.read_text(encoding="utf-8")) for cell, path in sources.items()}
    validation = validate_cells(states, expected)
    print(f"[summarise] validity: {validation['status']}", flush=True)

    session_path = (
        cells_dir.parent / "session.json"
        if cells_dir is not None and (cells_dir.parent / "session.json").exists()
        else None
    )
    historical = session_path is None
    summary: dict = {
        "experiment": EXP_DIR.name,
        "generated_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "status": validation["status"],
        "verdict": None,
        "validation": validation,
        "provenance": {
            "historical": historical,
            "limits": [
                "historical checkpoints carry no run identity or session "
                "recording; execution periods and code provenance at "
                "measurement time are not available"
            ]
            if historical
            else [],
        },
        "out_dir": str(out_dir),
        "cell_sources": {cell: str(path) for cell, path in sources.items()},
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

    session = json.loads(session_path.read_text(encoding="utf-8")) if session_path else None
    scored = {
        cell: [
            {**row, "metrics": _metrics_for_query(row["parent_ids"], queries[row["query_id"]])}
            for row in states[cell]["rows"]
        ]
        for cell in sources
    }
    counts = {cell: len(rows) for cell, rows in scored.items()}
    print(f"[summarise] cell sizes: {counts}", flush=True)

    aggregates = {cell: _aggregate(rows) for cell, rows in scored.items()}
    gates = _gates(plan, aggregates["combined_candidate"])
    verdict = "PASS" if all(g["pass"] for g in gates.values()) else "FAIL"
    failed = [name for name, gate in gates.items() if not gate["pass"]]
    interaction = _interaction(aggregates)

    if verdict == "PASS":
        headline = (
            "- All three frozen gates pass on the stacked path: the combined\n"
            f"  candidate holds mean R@5 at {gates['quality_recall_at_5']['measured']:.4f} and\n"
            f"  identifier-heavy R@10 at {gates['regression_identifier_r10']['measured']:.4f},\n"
            f"  inside a p95 of {gates['latency_p95_ms']['measured']:,.0f} ms.\n"
            f"- Interaction on R@5 is {interaction['interaction']:+.4f}: stacking the two\n"
            "  changes behaves close to additively on this workload.\n"
            "- This does not promote the query instruction. Experiment 26's gates do."
        )
    else:
        headline = (
            f"- **Negative result.** Failed gates: {', '.join(failed)}.\n"
            "- The stacked path is worse than the frozen bar the single-factor\n"
            "  arms were held to. Ship only the component that passed alone.\n"
            f"- Interaction on R@5 is {interaction['interaction']:+.4f}."
        )

    summary |= {
        "verdict": verdict,
        "failed_gates": failed,
        "headline": headline,
        "gates": gates,
        "metrics_by_cell": aggregates,
        "interaction": interaction,
        "query_token_cost": _query_token_cost(queries),
        "drift": _drift(aggregates),
        "execution": {
            "session": session,
            "periods_text": (
                "Execution periods were not recorded for the historical cells "
                "(provenance limit); the two measured cells were interleaved per "
                "query in one process."
                if session is None
                else f"Session {session.get('session_id', '?')}: "
                f"{len(session.get('periods', []))} recorded execution period(s)."
            ),
        },
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


def main() -> None:
    """Summarise validated cells into an explicit out directory."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="optional run directory whose cells/ subtree overrides the measured cells",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=EXP_DIR / "output/recovery-2026-09-10",
        help="distinct report destination; frozen historical outputs are never written",
    )
    args = parser.parse_args()
    cells_dir = args.run_dir / "cells" if args.run_dir is not None else None
    summarise_from(cells_dir, args.out_dir)


if __name__ == "__main__":
    main()
