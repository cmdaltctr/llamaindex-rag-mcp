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

    row_ids = [
        row["query_id"]
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("query_id"), str)
    ]
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
    validation: dict[str, dict] = {}
    id_sets: dict[str, set[str]] = {}
    for cell, state in states.items():
        rows = state.get("rows", []) if isinstance(state, dict) else None
        result = (
            classify_cell(rows, state.get("done", []), expected)
            if isinstance(state, dict)
            else {"status": "invalid", "reasons": ["checkpoint is not an object"]}
        )
        safe_rows = rows if isinstance(rows, list) else []
        validation[cell] = result | {"n_rows": len(safe_rows), "expected_n": len(expected)}
        id_sets[cell] = {
            row["query_id"]
            for row in safe_rows
            if isinstance(row, dict) and isinstance(row.get("query_id"), str)
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


def load_checkpoint_files(sources: dict[str, Path], expected: dict[str, str]) -> tuple[dict, dict]:
    """Read selected checkpoints and retain all validation and read-error reasons."""
    states: dict = {}
    errors: dict[str, str] = {}
    for cell, path in sources.items():
        try:
            states[cell] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            states[cell] = {"rows": [], "done": []}
            description = (
                "checkpoint file missing"
                if isinstance(exc, FileNotFoundError)
                else ("checkpoint cannot be read as JSON")
            )
            errors[cell] = f"{description}: {path}"
    validation = validate_cells(states, expected)
    for cell, reason in errors.items():
        validation["status"] = "invalid"
        validation["cells"][cell]["status"] = "invalid"
        validation["cells"][cell]["reasons"].append(reason)
        validation["pairing_reasons"].append(f"{cell}: {reason}")
    return states, validation


def summary_provenance(
    states: dict,
    measured: tuple[str, ...],
    run_dir: Path,
    plan_path: Path,
    gt_path: Path,
    historical_manifest: Path,
) -> tuple[dict, dict | None, dict, list[str]]:
    """Check measured cells against recorded session inputs without rerunning them.

    Legacy cells remain readable with explicit provenance limits. A session file
    cannot upgrade them into new evidence. Historical reference cells in a
    combined grid retain their separate provenance.
    """
    session_path = run_dir / "session.json"
    has_identity = any(
        isinstance(states[cell], dict)
        and ("run_identity" in states[cell] or "session_id" in states[cell])
        for cell in measured
    )
    historical = not session_path.exists() and not has_identity
    limits = []
    reasons: list[str] = []
    session = None
    manifest: dict = {}
    manifest_path = historical_manifest if historical else run_dir / "runtime_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("runtime manifest is not an object")
    except (OSError, UnicodeError, ValueError):
        reasons.append("runtime manifest is missing or invalid")
        manifest = {}

    if historical:
        limits.append(
            "Historical checkpoints lack run identity and recorded execution periods; "
            "their measurement-time code and session cannot be verified."
        )
    else:
        try:
            session = json.loads(session_path.read_text(encoding="utf-8"))
            if not isinstance(session, dict):
                raise ValueError("session is not an object")
            identity = session.get("run_identity")
            session_id = session.get("session_id")
            if not isinstance(identity, dict) or not isinstance(session_id, str) or not session_id:
                raise ValueError("session identity is missing")
            required = ("plan", "ground_truth", "corpus_manifest", "runtime_manifest")
            if not all(isinstance(identity.get(key), str) and identity[key] for key in required):
                raise ValueError("session input identity is incomplete")
            if not isinstance(identity.get("code"), dict) or not identity["code"]:
                raise ValueError("session code identity is missing")
            observed = {
                **identity,
                "plan": _sha256_file(plan_path),
                "ground_truth": _sha256_file(gt_path),
                "runtime_manifest": _sha256_value(manifest),
            }
            differing = identity_mismatches(identity, observed)
            if differing:
                reasons.append(f"session inputs differ on fields: {', '.join(differing)}")
            for cell in measured:
                state = states[cell]
                if not isinstance(state, dict) or state.get("run_identity") != identity:
                    reasons.append(f"{cell}: checkpoint run identity differs from session")
                if not isinstance(state, dict) or state.get("session_id") != session_id:
                    reasons.append(f"{cell}: checkpoint session_id differs from session")
            periods = session.get("periods")
            if not isinstance(periods, list) or not periods:
                reasons.append("session has no recorded execution periods")
        except (OSError, UnicodeError, ValueError):
            reasons.append("session record is missing or invalid")
            session = None
        limits.append(
            "Recorded corpus and code identities are compared between measured cells; "
            "this summary does not reconstruct or execute their historical environment."
        )
    references = sorted(set(states) - set(measured))
    if references:
        limits.append(
            "Reference cells retain separate historical provenance and are not part of "
            f"the measured session: {', '.join(references)}."
        )
    provenance = {"historical": historical, "limits": limits}
    return provenance, session, manifest, reasons


def create_report_directory(out_dir: Path, protected_dirs: list[Path]) -> Path:
    """Reserve a fresh report directory without writing inside checkpoint inputs."""
    if out_dir.is_symlink():
        raise ValueError("report destination must not be a symlink")
    destination = out_dir.resolve()
    if any(destination.is_relative_to(path.resolve()) for path in protected_dirs):
        raise ValueError("report destination is inside protected experiment inputs")
    destination.mkdir(parents=True, exist_ok=False)
    return destination


def write_report_text(path: Path, content: str) -> None:
    """Write a new report file exclusively; never replace existing evidence."""
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content)
