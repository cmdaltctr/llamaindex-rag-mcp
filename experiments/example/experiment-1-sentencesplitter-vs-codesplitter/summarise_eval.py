"""Summarise Experiment 1: structural integrity verdicts for H1-H3.

Reads ``output/cells/{S,C}.json`` plus the frozen fixture labels, computes
the protocol section 7 aggregates with per-stratum breakdowns (protocol
sections 6/15), applies the section 14 success gates, and writes
``output/summary.json``.  The optional H4 retrieval arm is reported as
NOT RUN (it requires an embedding runtime and is not a correctness gate).

Cut classification: each cut event names the definition it landed inside;
the summariser cross-references the fixture labels to split cuts into
``fit`` definitions (span <= code_max_chars) and ``oversized`` ones
(documented upstream recursion semantics, protocol section 16).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments._lib import stats  # noqa: E402

OUTPUT_DIR = SCRIPT_DIR / "output"
SUMMARY_PATH = OUTPUT_DIR / "summary.json"
BOOTSTRAP_SEED = 20260819


def load_cell(cell_id: str) -> dict[str, Any]:
    """Load one recorded cell payload."""
    return json.loads((OUTPUT_DIR / "cells" / f"{cell_id}.json").read_text(encoding="utf-8"))


def definition_spans_by_file() -> dict[str, dict[str, dict[str, Any]]]:
    """Return fixture id -> definition name -> label dict from the frozen labels."""
    manifest = json.loads((SCRIPT_DIR / "fixtures" / "manifest.json").read_text(encoding="utf-8"))
    return {
        fixture["id"]: {definition["name"]: definition for definition in fixture["definitions"]}
        for fixture in manifest["fixtures"]
    }


def classify_cuts(
    cell: dict[str, Any], spans: dict[str, dict[str, dict[str, Any]]]
) -> dict[str, Any]:
    """Split cut events into fit-definition and oversized-definition cuts."""
    fit_cuts: list[dict[str, Any]] = []
    oversized_cuts: list[dict[str, Any]] = []
    for event in cell["cut_events"]:
        definition = spans[event["file"]][event["definition"]]
        target = oversized_cuts if not definition["fits_under_ceiling"] else fit_cuts
        target.append(
            {
                "file": event["file"],
                "definition": event["definition"],
                "definition_span_chars": definition["span_chars"],
                "boundary_line": event["boundary_line"],
                "boundary_offset": event["boundary_offset"],
            }
        )
    return {"fit_definition_cuts": fit_cuts, "oversized_definition_cuts": oversized_cuts}


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate one cell's per-file rows into cell-level metrics."""
    total_boundaries = sum(row["metrics"]["total_boundaries"] for row in rows)
    cut_boundaries = sum(row["metrics"]["cut_boundaries"] for row in rows)
    fit_definitions = sum(row["metrics"]["definitions_fit_under_ceiling"] for row in rows)
    covered = sum(row["metrics"]["definitions_covered_whole"] for row in rows)
    chunk_lengths = [length for row in rows for length in row["metrics"]["chunk_char_lengths"]]
    return {
        "files": len(rows),
        "chunks_total": sum(row["metrics"]["chunk_count"] for row in rows),
        "chunk_chars_mean": round(sum(chunk_lengths) / len(chunk_lengths), 1),
        "chunk_chars_max": max(chunk_lengths),
        "total_boundaries": total_boundaries,
        "cut_boundaries": cut_boundaries,
        "structural_cut_rate": round(cut_boundaries / total_boundaries, 4)
        if total_boundaries
        else 0.0,
        "definitions_fit_under_ceiling": fit_definitions,
        "definitions_covered_whole": covered,
        "whole_definition_coverage": round(covered / fit_definitions, 4)
        if fit_definitions
        else None,
        "max_chars_violations": sum(row["metrics"]["max_chars_violations"] for row in rows),
        "max_chars_violations_unexplained": sum(
            row["metrics"]["max_chars_violations_unexplained"] for row in rows
        ),
        "fallback_count": sum(1 for row in rows if row["metrics"]["fallback"]),
    }


def strata(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    """Per-stratum aggregate for a blocking variable (language/complexity)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["metrics"][key], []).append(row)
    return {name: aggregate(group) for name, group in sorted(groups.items())}


def main() -> int:
    cell_s = load_cell("S")
    cell_c = load_cell("C")
    spans = definition_spans_by_file()

    cut_classification_s = classify_cuts(cell_s, spans)
    cut_classification_c = classify_cuts(cell_c, spans)

    agg_s = aggregate(cell_s["rows"])
    agg_c = aggregate(cell_c["rows"])

    h1_effective = sum(
        1 for row in cell_c["rows"] if row["metrics"]["effective_strategy"] == "code"
    )
    h1 = {
        "code_files_effective_code": h1_effective,
        "code_files_total": len(cell_c["rows"]),
        "fallback_count": agg_c["fallback_count"],
        "verdict": "PASS"
        if h1_effective == len(cell_c["rows"]) and agg_c["fallback_count"] == 0
        else "FAIL",
    }

    ci = stats.paired_bootstrap_ci(
        [row["metrics"]["cut_boundaries"] for row in cell_c["rows"]],
        [row["metrics"]["cut_boundaries"] for row in cell_s["rows"]],
        seed=BOOTSTRAP_SEED,
    )
    h2 = {
        "structural_cut_rate_code": agg_c["structural_cut_rate"],
        "structural_cut_rate_sentence": agg_s["structural_cut_rate"],
        "cut_boundaries_code": agg_c["cut_boundaries"],
        "cut_boundaries_sentence": agg_s["cut_boundaries"],
        "total_boundaries_code": agg_c["total_boundaries"],
        "total_boundaries_sentence": agg_s["total_boundaries"],
        "fit_definition_cuts_code": len(cut_classification_c["fit_definition_cuts"]),
        "fit_definition_cuts_sentence": len(cut_classification_s["fit_definition_cuts"]),
        "oversized_definition_cuts_code": len(cut_classification_c["oversized_definition_cuts"]),
        "paired_bootstrap_ci_cut_boundaries_code_minus_sentence": ci,
        "verdict": "PASS"
        if agg_c["structural_cut_rate"] < agg_s["structural_cut_rate"]
        else "FAIL",
    }

    h3 = {
        "max_chars_violations": agg_c["max_chars_violations"],
        "max_chars_violations_unexplained": agg_c["max_chars_violations_unexplained"],
        "violation_events": cell_c["violation_events"],
        "verdict": "PASS" if agg_c["max_chars_violations_unexplained"] == 0 else "FAIL",
    }

    summary = {
        "experiment_id": "example-experiment-1-sentencesplitter-vs-codesplitter",
        "protocol_version": "1.0",
        "hypotheses": {"H1_execution": h1, "H2_structural_integrity": h2, "H3_boundedness": h3},
        "H4_retrieval_sanity": "NOT RUN — optional arm; requires embedding runtime; "
        "H1-H3 are the correctness gates",
        "cells": {
            "S": {
                "aggregate": agg_s,
                "by_language": strata(cell_s["rows"], "language"),
                "by_complexity": strata(cell_s["rows"], "complexity"),
            },
            "C": {
                "aggregate": agg_c,
                "by_language": strata(cell_c["rows"], "language"),
                "by_complexity": strata(cell_c["rows"], "complexity"),
                "cut_classification": cut_classification_c,
            },
        },
        "sentence_cut_classification": cut_classification_s,
    }
    overall = (
        "PASS"
        if h1["verdict"] == "PASS" and h2["verdict"] == "PASS" and h3["verdict"] == "PASS"
        else "FAIL"
    )
    summary["status"] = overall

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"status": overall, "H1": h1["verdict"], "H2": h2["verdict"], "H3": h3["verdict"]}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
