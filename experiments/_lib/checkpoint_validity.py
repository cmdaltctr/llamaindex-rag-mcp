"""Checkpoint validity and run-identity contracts for retrieval experiments.

Shared by experiments 26 and 27 (repair tasks 4.1-4.5). The vocabulary
follows ``_lib.stats.VALID_CELL_STATUSES`` (complete / incomplete /
invalid): a smoke-sized subset of the declared query set is INCOMPLETE,
never a verdict; duplicates, unexpected ids, category drift, malformed
rows or a ``done``/``rows`` desync are INVALID.

Style follows ``_lib.preflight``: plain dicts, reason string lists,
standard library only.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

REQUIRED_ROW_KEYS = ("query_id", "category", "parent_ids", "latency_s")


def _reason(text: str) -> str:
    return text


def classify_cell(rows: object, done: object, expected: dict[str, str]) -> dict[str, object]:
    """Validate one cell's checkpoint against the declared observation set.

    ``expected`` maps query id to the ground-truth category label. A
    well-formed strict subset of ``expected`` is ``incomplete``; any
    structural defect is ``invalid``; exact membership is ``complete``.
    """
    reasons: list[str] = []
    if not isinstance(rows, list):
        return {"status": "invalid", "reasons": [_reason("rows is not a list")]}
    if not isinstance(done, list) or not all(isinstance(item, str) for item in done):
        return {"status": "invalid", "reasons": [_reason("done is not a list of query ids")]}

    seen: dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            reasons.append(_reason(f"row {index} is not an object"))
            continue
        for key in REQUIRED_ROW_KEYS:
            if key not in row:
                reasons.append(_reason(f"row {index} is missing {key}"))
        query_id = row.get("query_id")
        if not isinstance(query_id, str):
            reasons.append(_reason(f"row {index} query_id is not a string"))
            continue
        if query_id in seen:
            reasons.append(
                _reason(f"duplicate query id {query_id} (rows {seen[query_id]}, {index})")
            )
        seen[query_id] = index
        if query_id not in expected:
            reasons.append(_reason(f"unexpected query id {query_id} is not in the declared set"))
            continue
        if row.get("category") != expected[query_id]:
            reasons.append(
                _reason(
                    f"query {query_id} category {row.get('category')!r} does not match "
                    f"the declared category {expected[query_id]!r}"
                )
            )
        parent_ids = row.get("parent_ids")
        if not isinstance(parent_ids, list) or not all(isinstance(p, str) for p in parent_ids):
            reasons.append(_reason(f"query {query_id} parent_ids is not a list of strings"))
        latency = row.get("latency_s")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)):
            reasons.append(_reason(f"query {query_id} latency_s is not a number"))
        elif not math.isfinite(float(latency)):
            reasons.append(_reason(f"query {query_id} latency_s is not finite"))
        elif float(latency) < 0.0:
            reasons.append(_reason(f"query {query_id} latency_s is negative"))

    row_ids = [row.get("query_id") for row in rows if isinstance(row, dict)]
    if len(done) != len(row_ids) or set(done) != set(row_ids):
        reasons.append(
            _reason(f"done list ({len(done)} ids) is inconsistent with rows ({len(row_ids)} rows)")
        )

    if reasons:
        return {"status": "invalid", "reasons": reasons}
    missing = sorted(set(expected) - set(done))
    if missing:
        return {
            "status": "incomplete",
            "reasons": [_reason(f"missing {len(missing)} of {len(expected)} expected query ids")],
        }
    return {"status": "complete", "reasons": []}


def pairing_ids_mismatch(id_sets: dict[str, set[str]]) -> list[str]:
    """Reasons when paired cells do not cover the same query id sets.

    Equal row counts with different membership must be flagged before any
    paired effect is evaluated (spec scenario: equal counts hide different
    query membership).
    """
    if not id_sets:
        return []
    names = sorted(id_sets)
    reference = names[0]
    reasons: list[str] = []
    for name in names[1:]:
        if id_sets[name] != id_sets[reference]:
            reasons.append(
                _reason(
                    f"cells {reference!r} and {name!r} cover different query id sets; "
                    "equal counts cannot pair rows across different membership"
                )
            )
    return reasons


def validate_cells(states: dict[str, dict], expected: dict[str, str]) -> dict:
    """Validate every cell and the cross-cell pairing (repair tasks 4.2/4.3).

    Returns an overall status (``complete`` / ``incomplete`` / ``invalid``),
    per-cell results with row counts, and pairing reasons. Any invalid cell
    makes the whole set invalid. A membership mismatch between cells with
    EQUAL row counts is invalid (the spec scenario: equal counts hide
    different query membership); with unequal counts the honest aggregate
    for otherwise well-formed cells is incomplete — the run is partial, not
    corrupted. Only exact, consistent membership everywhere is complete.
    """
    validation = {
        cell: (
            classify_cell(state.get("rows", []), state.get("done", []), expected)
            | {"n_rows": len(state.get("rows", [])), "expected_n": len(expected)}
            if isinstance(state, dict)
            else {
                "status": "invalid",
                "reasons": [f"checkpoint is not an object: {type(state).__name__}"],
                "n_rows": 0,
                "expected_n": len(expected),
            }
        )
        for cell, state in states.items()
    }
    id_sets = {
        cell: {
            row.get("query_id")
            for row in (state.get("rows", []) if isinstance(state, dict) else [])
            if isinstance(row, dict)
        }
        for cell, state in states.items()
    }
    pairing = pairing_ids_mismatch(id_sets)
    counts_equal = len({v["n_rows"] for v in validation.values()}) <= 1
    if any(v["status"] == "invalid" for v in validation.values()):
        status = "invalid"
    elif pairing and counts_equal:
        status = "invalid"
    elif any(v["status"] == "incomplete" for v in validation.values()) or pairing:
        status = "incomplete"
    else:
        status = "complete"
    return {"status": status, "cells": validation, "pairing_reasons": pairing}


def validity_markdown_lines(summary: dict) -> list[str]:
    """Markdown block describing why a summary is not complete.

    Used by the experiment 27 report renderer. Experiment 26 renders an
    equivalent block locally (``_validation_lines``) without the
    loaded-reference-cells sentence, because it has no loaded cells; the
    two wordings are deliberately kept separate rather than merged
    behind a flag.
    """
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
        "from this state. Loaded reference cells, where present, are",
        "validated exactly like the locally measured cells. INCOMPLETE: the",
        "declared query set is not fully measured. INVALID: at least one",
        "cell is malformed, duplicated, mislabelled or covers a different",
        "query set.",
        "",
    ]
    return lines


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_value(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_identity(
    plan_path: Path,
    gt_path: Path,
    corpus_manifest_path: Path,
    runtime_manifest: dict,
    code_paths: list[Path],
) -> dict:
    """Deterministic identity binding plan, corpus, treatment and code.

    Deliberately timestamp-free so a resumed process recomputes the same
    identity; session timing lives beside it, not inside it.
    """
    return {
        "plan": _sha256_file(plan_path),
        "ground_truth": _sha256_file(gt_path),
        "corpus_manifest": _sha256_file(corpus_manifest_path),
        "runtime_manifest": _sha256_value(runtime_manifest),
        "code": {str(path): _sha256_file(path) for path in code_paths},
    }


def identity_mismatches(saved: dict, current: dict) -> list[str]:
    """Names of identity fields that differ between two identity blocks."""
    return [key for key in sorted(set(saved) | set(current)) if saved.get(key) != current.get(key)]


def evaluate_resume(
    cell_states: dict[str, dict | None], current_identity: dict
) -> dict[str, object]:
    """Decide whether saved checkpoints may resume into the current run.

    A checkpoint without a ``run_identity`` block is historical evidence:
    readable, never resumable into a new run. A mismatched identity is
    refused with the differing fields named.
    """
    reasons: list[str] = []
    for cell, state in cell_states.items():
        if state is None:
            continue
        if not isinstance(state, dict):
            reasons.append(_reason(f"cell {cell!r} checkpoint is not an object"))
            continue
        if "run_identity" not in state:
            reasons.append(
                _reason(
                    f"cell {cell!r} is historical evidence without run identity; "
                    "historical checkpoints are not resumable into new runs"
                )
            )
            continue
        differing = identity_mismatches(state["run_identity"], current_identity)
        if differing:
            reasons.append(
                _reason(f"cell {cell!r} run identity differs on fields: {', '.join(differing)}")
            )
    if reasons:
        return {"action": "refuse", "reasons": reasons}
    return {"action": "resume", "reasons": []}
