"""Summarise Example Experiment 4: per-hypothesis verdicts (task 5.4).

Computes the protocol §14 success-gate verdicts from the raw battery
records against the committed qrels:

- H1 store isolation: querying either store's ``documents`` collection
  never yields rows belonging to the other store, and the two
  same-named collections hold two distinct cache entries at the
  collision step.
- H2 collection isolation: within store A, ``documents`` and ``other``
  never share cache state or leak rows.
- H3 stable reuse: repeated unmutated queries cause zero additional
  cache builds.
- H4 mutation invalidation: exactly the affected namespace rebuilds
  after each mutation; unaffected namespace build totals stay at their
  expected counts.
- H5 single generation owner: every successful logical mutation
  (direct-store and production-orchestration paths alike) advances the
  generation by exactly +1.

Also provides ``--canonicalise`` for the byte-identical rerun proof.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent

# Battery step -> mutation phase (mirrors battery.py's sequence and the
# committed qrels' phase-dependent expectations).
_STEP_PHASE = {
    "s1": "initial",
    "s2": "initial",
    "s3": "initial",
    "s4": "initial",
    "s3x": "initial",
    "s6a": "post_direct_upsert",
    "s6b": "post_direct_upsert",
    "s7a": "post_direct_upsert",
    "s7b": "post_direct_upsert",
    "s8a": "post_filtered_delete",
    "s8b": "post_filtered_delete",
    "s9a-q": "post_orchestration_write",
    "s9b-q": "post_orchestration_remove",
    "s9c-q": "post_collection_drop",
    "s9d-q": "post_recreate",
}

# Expected per-query cache build delta by step (protocol H3/H4).
_STEP_BUILD_DELTA = {
    "s1": 1,
    "s2": 0,
    "s3": 1,
    "s4": 1,
    "s3x": 0,
    "s6a": 1,
    "s6b": 0,
    "s7a": 0,
    "s7b": 0,
    "s8a": 1,
    "s8b": 0,
    "s9a-q": 1,
    "s9b-q": 1,
    "s9c-q": 1,
    "s9d-q": 1,
}

# Expected final build totals per namespace (initial build + one build
# per invalidating mutation of that namespace).
_EXPECTED_TOTAL_BUILDS = {
    "A/documents": 5,
    "B/documents": 1,
    "A/other": 3,
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# (query term, namespace) pairs whose expected result is empty after
# the collection-drop step of the battery.
_POST_DROP_EMPTY = {("gamma_only", "A/other")}


def _expected_ids(qrels: dict[str, Any], namespace: str, token: str, step: str) -> list[str]:
    phase = _STEP_PHASE[step]
    if token in qrels["stable_token_expected_ids"]:
        expected = qrels["stable_token_expected_ids"][token].get(namespace, [])
        dropped = (token, namespace) in _POST_DROP_EMPTY and phase == "post_collection_drop"
        if dropped:
            return []
        return list(expected)
    phases = qrels["mutation_token_expected_ids"][token][namespace]
    if isinstance(phases, list):
        return list(phases)
    if phase == "initial":
        phase = {
            "delta_only": "pre_mutation",
            "epsilon_only": "pre_orchestration",
        }[token]
    return list(phases.get(phase, []))


def _id_owner(qrels: dict[str, Any]) -> dict[str, str]:
    owner: dict[str, str] = {}
    for namespace, spec in qrels["namespaces"].items():
        for doc_id in spec["stable_ids"]:
            owner[doc_id] = namespace
    owner["a_d_delta"] = "A/documents"
    owner["orch_eps_1"] = "A/documents"
    return owner


def _h1_h2(raw: dict[str, Any], qrels: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    owner = _id_owner(qrels)
    cross_store: list[str] = []
    cross_collection: list[str] = []
    mismatches: list[str] = []
    distinct_documents_entries_observed = False
    for row in raw["rows"]:
        step = row["cell_step"]
        metrics = row["metrics"]
        expected = _expected_ids(qrels, row["namespace"], row["token"], step)
        observed = metrics["result_ids"]
        if sorted(observed) != sorted(expected):
            mismatches.append(
                f"{row['cell_id']}/{step} {row['namespace']} x {row['token']}: "
                f"{observed} != {expected}"
            )
        for doc_id in observed:
            if owner.get(doc_id, "?") != row["namespace"]:
                target = owner.get(doc_id, "?")
                same_store = target.split("/")[0] == row["namespace"].split("/")[0]
                bucket = cross_collection if same_store else cross_store
                bucket.append(
                    f"{row['cell_id']}/{step}: {doc_id} ({target}) leaked into {row['namespace']}"
                )
        if row["namespace"] in ("A/documents", "B/documents") and row["token"] in (
            "alpha_only",
            "beta_only",
        ):
            distinct_documents_entries_observed = (
                distinct_documents_entries_observed or metrics["documents_key_entries"] >= 2
            )
    h1 = {
        "cross_store_contaminations": cross_store,
        "distinct_documents_cache_entries_observed": distinct_documents_entries_observed,
        "pass": not cross_store and distinct_documents_entries_observed,
    }
    h2 = {
        "cross_collection_contaminations": cross_collection,
        "expected_id_mismatches": mismatches,
        "pass": not cross_collection and not mismatches,
    }
    return h1, h2


def _h3_h4(raw: dict[str, Any], battery: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    reuse_failures: list[str] = []
    invalidation_failures: list[str] = []
    for row in raw["rows"]:
        step = row["cell_step"]
        metrics = row["metrics"]
        build_delta = metrics["build_count_after"] - metrics["build_count_before"]
        if build_delta != _STEP_BUILD_DELTA[step]:
            bucket = reuse_failures if _STEP_BUILD_DELTA[step] == 0 else invalidation_failures
            bucket.append(
                f"{row['cell_id']}/{step} {row['namespace']} x {row['token']}: "
                f"build delta {build_delta} != {_STEP_BUILD_DELTA[step]}"
            )
    total_failures: list[str] = []
    for cell_id, result in sorted(battery.items()):
        for namespace, want_total in _EXPECTED_TOTAL_BUILDS.items():
            observed = result["build_counters"].get(
                f"{namespace.split('/')[0]}::{namespace.split('/')[1]}"
            )
            if observed != want_total:
                total_failures.append(
                    f"{cell_id}/{namespace}: total builds {observed} != {want_total}"
                )
    h3 = {"reuse_failures": reuse_failures, "pass": not reuse_failures}
    h4 = {
        "invalidation_failures": invalidation_failures,
        "unaffected_totals_failures": total_failures,
        "pass": not invalidation_failures and not total_failures,
    }
    return h3, h4


def _h5(battery: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    comparison: dict[str, dict[str, int]] = {}
    for cell_id, result in sorted(battery.items()):
        for record in result["mutation_trace"]:
            if record["generation_delta"] != 1:
                failures.append(
                    f"{cell_id}/{record['step']} ({record['kind']}): "
                    f"generation delta {record['generation_delta']} != 1"
                )
            comparison.setdefault(record["kind"], set()).add(record["generation_delta"])
    delta_by_kind = {kind: sorted(values) for kind, values in comparison.items()}
    direct_upsert = delta_by_kind.get("direct upsert_precomputed")
    orch_write = delta_by_kind.get("orchestration embed_and_write_async")
    direct_delete = delta_by_kind.get("direct delete_where")
    orch_remove = delta_by_kind.get("orchestration remove_document")
    if direct_upsert != [1] or orch_write != [1]:
        failures.append(f"direct {direct_upsert} vs orchestration {orch_write} write deltas")
    if direct_delete != [1] or orch_remove != [1]:
        failures.append(f"direct {direct_delete} vs orchestration {orch_remove} delete deltas")
    return {
        "deltas_by_mutation_kind": delta_by_kind,
        "failures": failures,
        "pass": not failures,
    }


def summarise(raw: dict[str, Any], qrels: dict[str, Any]) -> dict[str, Any]:
    h1, h2 = _h1_h2(raw, qrels)
    h3, h4 = _h3_h4(raw, raw["battery_results"])
    h5 = _h5(raw["battery_results"])
    summary = {
        "experiment_id": raw["experiment_id"],
        "protocol_version": raw["protocol_version"],
        "H1_store_isolation": h1,
        "H2_collection_isolation": h2,
        "H3_stable_reuse": h3,
        "H4_mutation_invalidation": h4,
        "H5_single_generation_owner": h5,
        "cache_key_mechanism": raw["battery_results"][next(iter(raw["battery_results"]))][
            "cache_key_mechanism"
        ],
        "cells": {cell_id: record["status"] for cell_id, record in raw["cells"].items()},
    }
    summary["status"] = (
        "PASS"
        if all(
            summary[h]["pass"]
            for h in (
                "H1_store_isolation",
                "H2_collection_isolation",
                "H3_stable_reuse",
                "H4_mutation_invalidation",
                "H5_single_generation_owner",
            )
        )
        and set(summary["cells"].values()) == {"complete"}
        else "FAIL"
    )
    return summary


def _canonicalise(value: Any) -> Any:
    """Drop wall-clock fields and random cleanup paths; round floats."""
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
        args.canonicalise.write_text(
            json.dumps(_canonicalise(raw), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return
    qrels = _load(SCRIPT_DIR / "fixtures" / "qrels.json")
    summary = summarise(raw, qrels)
    out = args.raw_path.parent / "results.summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"status={summary['status']} -> {out}", flush=True)
    for hypothesis in (
        "H1_store_isolation",
        "H2_collection_isolation",
        "H3_stable_reuse",
        "H4_mutation_invalidation",
        "H5_single_generation_owner",
    ):
        verdict = summary[hypothesis]
        print(f"{hypothesis}: {'PASS' if verdict['pass'] else 'FAIL'}", flush=True)
        for key, value in verdict.items():
            if isinstance(value, list) and value:
                print(f"  {key}: {value[:5]}", flush=True)


if __name__ == "__main__":
    main()
