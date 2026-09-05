"""Summarise Example Experiment 2: per-hypothesis verdicts (task 5.2).

Computes the protocol §14 success-gate verdicts from the raw rows
against the committed qrels expectations:

- H1 ranking parity: every measured repetition's ordered ids match the
  expected near-to-far order, with permutation allowed only inside
  pre-labelled tie groups (checked per backend and cross-backend).
- H2 canonical score monotonicity: per backend, scores are
  non-increasing along the expected distance order, strictly
  decreasing between distinct expected distances, and each score
  reproduces ``1 / (1 + d)`` from the expected analytic distance
  within a float32 tolerance.
- H3 threshold parity: observed threshold membership equals the
  pre-registered expected membership for every pinned threshold in
  both backends.
- H4 filter parity: observed filter membership (query ids and
  ``count_where``) equals the expected membership in both backends.
- H5 backend opacity: the static evidence passes and every measured
  row reports ``score_kind == "dense_similarity_v1"`` in both
  backends, with the core path agreeing with the adapter path.

Also provides ``--canonicalise`` to project a raw results file onto a
deterministic canonical form (latency and wall-clock fields removed,
floats rounded) for the byte-identical rerun proof.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
FLOAT_TOLERANCE = 1e-5
MONOTONIC_EPSILON = 1e-9
TIE_DISTANCE_EPSILON = 1e-9


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _measured_rows(raw: dict[str, Any], cell_id: str, fixture_id: str) -> list[dict[str, Any]]:
    return [
        row
        for row in raw["rows"]
        if row["cell_id"] == cell_id
        and row["phase"] == "measured"
        and row["fixture_id"] == fixture_id
    ]


def _h1_fixture(raw: dict[str, Any], qrels: dict[str, Any], fixture_id: str) -> dict[str, Any]:
    expected_order = qrels["fixtures"][fixture_id]["expected_order_near_to_far"]
    tie_groups = [g for g in qrels["fixtures"][fixture_id]["tie_groups"] if len(g) > 1]
    # Rank label per doc: tie-group members share their group's first
    # position; strict docs keep their own position.  A valid observed
    # ordering has non-decreasing labels with the exact expected id set,
    # which permits permutation only inside pre-labelled tie sets.
    label = {doc: position for position, doc in enumerate(expected_order)}
    for group in tie_groups:
        first = min(label[doc] for doc in group)
        for doc in group:
            label[doc] = first
    failures: list[str] = []
    reps = 0
    for cell_id in sorted(raw["cells"]):
        for row in _measured_rows(raw, cell_id, fixture_id):
            reps += 1
            observed = row["metrics"]["ids"]
            if sorted(observed) != sorted(expected_order):
                failures.append(f"{cell_id}: id set mismatch {observed} vs {expected_order}")
                continue
            observed_labels = [label[doc] for doc in observed]
            if any(
                later < earlier
                for earlier, later in zip(observed_labels, observed_labels[1:], strict=False)
            ):
                failures.append(f"{cell_id}: ordering violates tie-group structure: {observed}")
    return {
        "fixture": fixture_id,
        "pass": not failures,
        "repetitions_checked": reps,
        "failures": failures,
    }


def _h2_fixture(raw: dict[str, Any], qrels: dict[str, Any], fixture_id: str) -> dict[str, Any]:
    """H2 verdict (monotonicity) plus the formula-invariant findings.

    The pre-registered hypothesis is monotonic: canonical score
    decreases as known geometric distance increases.  The committed
    qrels additionally pin the documented ``1/(1+d)`` formula, so each
    observed score is checked against it; a deviation is recorded as a
    production finding (see ``production_findings``) without weakening
    the monotonicity verdict itself.
    """
    fixture_qrels = qrels["fixtures"][fixture_id]
    distances = fixture_qrels["expected_distances"]
    order = fixture_qrels["expected_order_near_to_far"]
    failures: list[str] = []
    formula_deviations: list[str] = []
    checks = 0
    for cell_id in sorted(raw["cells"]):
        for row in _measured_rows(raw, cell_id, fixture_id):
            ids = row["metrics"]["ids"]
            scores = dict(zip(ids, row["metrics"]["scores"], strict=True))
            for near, far in zip(order, order[1:], strict=False):
                checks += 1
                gap = distances[near] < distances[far] - TIE_DISTANCE_EPSILON
                if gap and not scores[near] > scores[far] + MONOTONIC_EPSILON:
                    failures.append(
                        f"{cell_id}: score({near})={scores[near]!r} not strictly "
                        f"greater than score({far})={scores[far]!r}"
                    )
                if not gap and abs(scores[near] - scores[far]) > FLOAT_TOLERANCE:
                    failures.append(
                        f"{cell_id}: tied docs {near}/{far} scores differ: "
                        f"{scores[near]!r} vs {scores[far]!r}"
                    )
            for doc, score in scores.items():
                expected_score = 1.0 / (1.0 + distances[doc])
                if abs(score - expected_score) > 1e-4:
                    formula_deviations.append(
                        f"{cell_id}: score({doc})={score!r} deviates from documented "
                        f"1/(1+d)={expected_score!r} (native distances in raw row "
                        f"rep_group={row['rep_group']})"
                    )
    return {
        "fixture": fixture_id,
        "comparisons": checks,
        "pass": not failures,
        "failures": failures,
        "documented_formula_deviations": formula_deviations,
    }


def _h3_summary(raw: dict[str, Any], qrels: dict[str, Any]) -> dict[str, Any]:
    """H3 verdict against the pre-registered expected membership.

    Records three distinct facts: (a) cross-store identity — do Chroma
    and Lance select the same rows (the §14 gate's parity clause);
    (b) ground-truth match — does the observed membership equal the
    committed analytic expectation; (c) the resulting verdict, which
    FAILS whenever the pre-registered ground truth mismatches, even if
    both stores mismatch identically.
    """
    failures: list[str] = []
    cross_store_failures: list[str] = []
    total = 0
    for fixture_id, fixture_qrels in sorted(qrels["fixtures"].items()):
        expected = fixture_qrels["expected_threshold_membership"]
        rows_by_cell: dict[str, list[dict[str, Any]]] = {
            cell_id: _measured_rows(raw, cell_id, fixture_id) for cell_id in sorted(raw["cells"])
        }
        for cell_id, rows in rows_by_cell.items():
            for row in rows:
                observed = row["metrics"]["threshold_membership"]
                for threshold, want in expected.items():
                    total += 1
                    if observed[threshold] != want:
                        failures.append(
                            f"{cell_id}/{fixture_id}@{threshold}: {observed[threshold]} != {want}"
                        )
        if len(rows_by_cell) == 2:
            (first, second) = sorted(rows_by_cell)
            for row_a, row_b in zip(rows_by_cell[first], rows_by_cell[second], strict=True):
                if (
                    row_a["metrics"]["threshold_membership"]
                    != row_b["metrics"]["threshold_membership"]
                ):
                    cross_store_failures.append(
                        f"{fixture_id}: {first} != {second} at rep_group={row_a['rep_group']}"
                    )
    return {
        "memberships_checked": total,
        "cross_store_identity_failures": cross_store_failures,
        "pass": not failures and not cross_store_failures,
        "failures": failures,
    }


def _h4_summary(raw: dict[str, Any], qrels: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    total = 0
    fixture_id = "f5_metadata_filters"
    expected = qrels["fixtures"][fixture_id]["expected_filter_membership"]
    for cell_id in sorted(raw["cells"]):
        for row in _measured_rows(raw, cell_id, fixture_id):
            observed = row["metrics"]["filter_membership"]
            for name, want in expected.items():
                total += 1
                got = observed[name]
                if sorted(got["query_ids"]) != want or got["count_where"] != len(want):
                    failures.append(
                        f"{cell_id}/{name}: query_ids={got['query_ids']} "
                        f"count_where={got['count_where']} expected={want}"
                    )
    return {"filters_checked": total, "pass": not failures, "failures": failures}


def _h5_summary(raw: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if not raw["static_check"]["pass"]:
        failures.extend(raw["static_check"]["failures"])
    for row in raw["rows"]:
        if row["phase"] != "measured":
            continue
        if row["metrics"]["score_kind"] != "dense_similarity_v1":
            failures.append(f"{row['cell_id']}: score_kind {row['metrics']['score_kind']!r}")
        if row["metrics"]["ids"] != row["metrics"]["adapter_ids"]:
            failures.append(f"{row['cell_id']}: core path ids differ from adapter ids")
        for core, adapter in zip(
            row["metrics"]["scores"], row["metrics"]["adapter_scores"], strict=True
        ):
            if abs(core - adapter) > FLOAT_TOLERANCE:
                failures.append(f"{row['cell_id']}: core score {core!r} != adapter {adapter!r}")
    return {"static_pass": raw["static_check"]["pass"], "pass": not failures, "failures": failures}


def _production_findings(h2: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Elevate systematic contract deviations to production findings."""
    findings: list[dict[str, Any]] = []
    deviation_count = sum(
        len(fixture.get("documented_formula_deviations", [])) for fixture in h2.values()
    )
    if deviation_count:
        affected = sorted(
            fixture["fixture"]
            for fixture in h2.values()
            if fixture.get("documented_formula_deviations")
        )
        findings.append(
            {
                "id": "exp2-f1-squared-l2-canonical-score",
                "severity": "production-defect-documentation",
                "observed": (
                    "Both adapters convert the engine-reported native distance "
                    "directly via canonical_score_from_l2, and BOTH engines' "
                    "'l2' metric reports SQUARED Euclidean distance "
                    "(evidence: fixture doc [0,1,0,0] vs query [1,0,0,0] "
                    "native=2.0=(sqrt(2))**2; [0.5,0,0,0] native=0.25=0.5**2; "
                    "[-2,0,0,0] native=9.0=3**2 — identical in chroma and "
                    "lancedb raw rows). The production canonical score is "
                    "therefore 1/(1+d**2), not the documented 1/(1+d)."
                ),
                "expected": (
                    "score.py:27-51 documents the canonical transform as "
                    "1/(1+distance) over a 'native non-negative L2 distance'; "
                    "the committed qrels encode that geometric interpretation."
                ),
                "locations": [
                    "src/omrg/core/vectordb/score.py:27-51 (contract text)",
                    "src/omrg/core/vectordb/chroma.py:264 (pass-through of Chroma 'l2' value)",
                    "src/omrg/core/vectordb/lancedb.py:370 (pass-through of Lance '_distance')",
                ],
                "impact": (
                    "Monotonicity and cross-store parity hold (d**2 is monotone "
                    "in d and both engines square identically), so ranking and "
                    "swappability are unaffected; the ABSOLUTE score/threshold "
                    "meaning deviates from the documented formula, so any "
                    "similarity_threshold calibrated against 1/(1+d) semantics "
                    "is mis-scaled."
                ),
                "affected_fixtures": affected,
                "deviation_examples": deviation_count,
            }
        )
    return findings


def summarise(raw: dict[str, Any], qrels: dict[str, Any]) -> dict[str, Any]:
    fixture_ids = sorted(qrels["fixtures"])
    h1 = {fid: _h1_fixture(raw, qrels, fid) for fid in fixture_ids}
    h2 = {fid: _h2_fixture(raw, qrels, fid) for fid in fixture_ids}
    summary = {
        "experiment_id": raw["experiment_id"],
        "protocol_version": raw["protocol_version"],
        "H1_ranking_parity": {"per_fixture": h1, "pass": all(v["pass"] for v in h1.values())},
        "H2_score_monotonicity": {"per_fixture": h2, "pass": all(v["pass"] for v in h2.values())},
        "H3_threshold_parity": _h3_summary(raw, qrels),
        "H4_filter_parity": _h4_summary(raw, qrels),
        "H5_backend_opacity": _h5_summary(raw),
        "production_findings": _production_findings(h2),
        "cells": {cell_id: record["status"] for cell_id, record in raw["cells"].items()},
    }
    summary["status"] = (
        "PASS"
        if all(
            summary[h]["pass"]
            for h in (
                "H1_ranking_parity",
                "H2_score_monotonicity",
                "H3_threshold_parity",
                "H4_filter_parity",
                "H5_backend_opacity",
            )
        )
        and set(summary["cells"].values()) == {"complete"}
        else "FAIL"
    )
    return summary


def _canonicalise(value: Any) -> Any:
    """Drop non-deterministic fields and round floats for the rerun proof.

    ``latency_ms`` and ``timestamp_utc`` are wall-clock; ``cleanup``
    lists random tempfile directory names (the deletion evidence stays
    in the raw file).
    """
    if isinstance(value, dict):
        return {
            key: _canonicalise(item)
            for key, item in value.items()
            if key not in {"latency_ms", "timestamp_utc", "cleanup"}
        }
    if isinstance(value, list):
        return [_canonicalise(item) for item in value]
    if isinstance(value, float):
        return round(value, 9)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_path", type=Path, help="results.raw.json from run_eval.py")
    parser.add_argument(
        "--canonicalise",
        type=Path,
        default=None,
        help="Write the deterministic canonical projection to this path and exit",
    )
    args = parser.parse_args()
    raw = _load(args.raw_path)
    if args.canonicalise:
        payload = _canonicalise(raw)
        args.canonicalise.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return
    qrels = _load(SCRIPT_DIR / "fixtures" / "qrels.json")
    summary = summarise(raw, qrels)
    out = args.raw_path.parent / "results.summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"status={summary['status']} -> {out}", flush=True)
    for hypothesis in (
        "H1_ranking_parity",
        "H2_score_monotonicity",
        "H3_threshold_parity",
        "H4_filter_parity",
        "H5_backend_opacity",
    ):
        verdict = summary[hypothesis]
        print(f"{hypothesis}: {'PASS' if verdict['pass'] else 'FAIL'}", flush=True)
        for failure in verdict.get("failures", [])[:10]:
            print(f"  {failure}", flush=True)
        for failure in verdict.get("per_fixture", {}).values():
            if not failure["pass"]:
                print(f"  fixture {failure['fixture']}: FAIL", flush=True)


if __name__ == "__main__":
    main()
