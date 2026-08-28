"""Summarise Experiment 7: cap units, prefix coverage, granularity verdicts.

Reads ``output/cells/*.json``, the frozen ground truth
``fixtures/expected_chunks.json``, and the pre-registration
``fixtures/manifest.json``; applies the protocol section 14 success gates
for H1-H5; writes ``output/summary.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = SCRIPT_DIR / "output"
SUMMARY_PATH = OUTPUT_DIR / "summary.json"


def load_cells() -> list[dict[str, Any]]:
    """Load every recorded cell payload in id order."""
    paths = sorted((OUTPUT_DIR / "cells").glob("*.json"))
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def load_manifests() -> dict[str, dict[str, Any]]:
    """Load the per-cell runtime manifests."""
    paths = sorted((OUTPUT_DIR / "manifests").glob("*.manifest.json"))
    return {
        path.name.removesuffix(".manifest.json"): json.loads(path.read_text(encoding="utf-8"))
        for path in paths
    }


def main() -> int:
    cells = load_cells()
    manifests = load_manifests()
    expected = json.loads(
        (SCRIPT_DIR / "fixtures" / "expected_chunks.json").read_text(encoding="utf-8")
    )
    pre_registration = json.loads(
        (SCRIPT_DIR / "fixtures" / "manifest.json").read_text(encoding="utf-8")
    )

    per_cell = []
    h1_ok = h2_ok = h3_ok = h5_ok = True
    for cell in cells:
        metrics = cell["rows"][0]["metrics"]
        document = metrics["document"]
        cap = metrics["cap"]
        expected_total = metrics["expected_total_chunks"]
        observed = metrics["observed_selected_chunks"]
        pre_registered = pre_registration["documents"][document]["expected_aggregation"]
        final_metadata = metrics["final_metadata"]

        cell_h1 = observed == min(cap, expected_total)
        cell_h2 = metrics["selected_hashes_match_first_n"]
        cell_h3 = metrics["final_metadata_uniform"] and final_metadata == {
            "category": pre_registered["category"],
            "keywords": pre_registered["keywords_flat"],
            "summary": pre_registered["summary"],
            "document_title": pre_registered["document_title"],
        }
        cell_h5 = metrics["calls_match_analytic"]

        h1_ok = h1_ok and cell_h1
        h2_ok = h2_ok and cell_h2
        h3_ok = h3_ok and cell_h3
        h5_ok = h5_ok and cell_h5
        per_cell.append(
            {
                "cell_id": cell["cell_id"],
                "cap": cap,
                "document": document,
                "total_chunks": expected_total,
                "tail_chunks_beyond_cap": expected_total - observed,
                "observed_selected_chunks": observed,
                "selected_hashes_match_first_n": cell_h2,
                "final_metadata_uniform_and_pre_registered": cell_h3,
                "final_metadata": final_metadata,
                "fake_llm_calls": metrics["fake_llm_total_calls"],
                "expected_llm_calls_analytic": metrics["expected_llm_calls_analytic"],
                "calls_match_analytic": cell_h5,
            }
        )

    h4_manifest_ok = all(
        manifest.get("metadata_granularity") == "file_aggregate" for manifest in manifests.values()
    )
    h4 = {
        "manifest_declaration_ok": h4_manifest_ok,
        "production_runtime_diagnostic_exists": False,
        "gap_note": (
            "Production has no runtime attribute exposing the persisted metadata "
            "granularity; H4 is satisfied via the manifest declaration "
            "(metadata_granularity=file_aggregate) plus the Stage 1 documentation "
            "correction (tasks 1.3.3) and verified file-level behaviour in H3. "
            "Reported as a gap, not worked around."
        ),
        "verdict": "PASS" if h4_manifest_ok else "FAIL",
    }

    # H5 tail-independence evidence: identical caps on the two documents
    # (different tails: 24 vs 16 total chunks) must produce identical call
    # counts.
    calls_by_cap: dict[int, set[int]] = {}
    for entry in per_cell:
        calls_by_cap.setdefault(entry["cap"], set()).add(entry["fake_llm_calls"])
    tail_independent = all(len(counts) == 1 for counts in calls_by_cap.values())

    hypotheses = {
        "H1_cap_unit": {
            "rule": "selected chunks == min(cap, total chunks), in chunk units",
            "verdict": "PASS" if h1_ok else "FAIL",
        },
        "H2_prefix_coverage": {
            "rule": "selected chunk hashes are exactly the first N ground-truth hashes",
            "verdict": "PASS" if h2_ok else "FAIL",
        },
        "H3_file_level_persisted_semantics": {
            "rule": "every final chunk carries the pre-registered aggregated file-level metadata",
            "verdict": "PASS" if h3_ok else "FAIL",
        },
        "H4_granularity_identified": h4,
        "H5_bounded_cost": {
            "rule": (
                "call count == 2N + min(5, N) + 1 and identical across documents with "
                "different tails at the same cap"
            ),
            "calls_by_cap": {
                str(cap): sorted(counts) for cap, counts in sorted(calls_by_cap.items())
            },
            "tail_independent": tail_independent,
            "verdict": "PASS" if h5_ok and tail_independent else "FAIL",
        },
    }
    overall = "PASS" if all(h["verdict"] == "PASS" for h in hypotheses.values()) else "FAIL"

    summary = {
        "experiment_id": "example-experiment-7-metadata-cap-and-granularity",
        "protocol_version": "1.0",
        "status": overall,
        "hypotheses": hypotheses,
        "cells": per_cell,
        "token_char_divergence": {
            document: entry["token_char_divergence_ratio"]
            for document, entry in expected["documents"].items()
        },
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({name: h["verdict"] for name, h in hypotheses.items()} | {"status": overall}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
