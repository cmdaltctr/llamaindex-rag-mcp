"""Summarise Experiment 5 results: hypotheses H1-H5 (protocol section 14).

Reads ``output/eval_results.json`` (written by ``run_eval.py``) and
evaluates, over complete cells only:

* **H1 — device parity:** per-query, per-pass max absolute score delta
  and ranking equality between ``torch_cpu`` and ``torch_mps``
  (paired by query id and pass index); gate: 100% ranking equality and
  max delta <= 1e-4.
* **H2 — MPS speed:** median steady-state per-query latency contrast
  (warm-up excluded via ``split_warmup``); gate: median MPS <= 0.8 x
  median CPU, with a paired bootstrap CI (seed 20260819).
* **H3 — operational bound:** peak RSS <= 2x and cold start <= 3x the
  ``onnx_cpu`` cell.
* **H4 — backend attribution:** every ``onnx_cpu`` vs ``torch_cpu``
  ranking disagreement cross-checked against ``torch_cpu`` vs
  ``torch_mps`` before attribution (protocol section 19).
* **H5 — manifest truth:** every completed repetition proved its
  effective provider/device before timing (route facts present in the
  manifest).

Non-complete cells are never aggregated; their statuses propagate into
the summary verbatim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import harness  # noqa: E402 — needs SCRIPT_DIR on sys.path first

#: H1 pre-registered numerical tolerance (protocol section 2).
SCORE_TOLERANCE = 1e-4

#: H2 pre-registered speed gate (protocol section 14).
MPS_SPEED_RATIO_GATE = 0.8

#: H3 pre-registered resource gates (protocol section 14).
RSS_RATIO_GATE = 2.0
COLD_START_RATIO_GATE = 3.0


def _repetition_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(result.get("repetition_records", []))


def _complete_reps(records: list[dict[str, Any]], cell_id: str) -> list[dict[str, Any]]:
    return [
        rep for rep in records if rep.get("cell_id") == cell_id and rep.get("status") == "complete"
    ]


def _measured_rows(reps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from experiments._lib import stats as stats_lib

    rows: list[dict[str, Any]] = []
    for rep in reps:
        _, measured = stats_lib.split_warmup(rep.get("rows", []))
        rows.extend(measured)
    return rows


def _latencies_by_query(rows: list[dict[str, Any]]) -> dict[str, list[float]]:
    by_query: dict[str, list[float]] = {}
    for row in rows:
        by_query.setdefault(row["query_id"], []).append(float(row["latency_ms"]))
    return by_query


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _scores_by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, int, int], dict]:
    """Index measured rows by (query_id, repetition, pass_index)."""
    return {(row["query_id"], row["repetition"], row["pass_index"]): row["metrics"] for row in rows}


def _max_abs_delta_and_rankings(
    rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]]
) -> dict[str, Any]:
    """Paired parity facts between two cells over identical keys."""
    scores_a = _scores_by_key(rows_a)
    scores_b = _scores_by_key(rows_b)
    shared = sorted(set(scores_a) & set(scores_b))
    max_delta = 0.0
    ranking_equal = 0
    ranking_disagreements: list[dict[str, Any]] = []
    for key in shared:
        metrics_a, metrics_b = scores_a[key], scores_b[key]
        common_docs = set(metrics_a["scores"]) & set(metrics_b["scores"])
        for doc_id in common_docs:
            delta = abs(metrics_a["scores"][doc_id] - metrics_b["scores"][doc_id])
            if delta > max_delta:
                max_delta = delta
        if metrics_a["ranking"] == metrics_b["ranking"]:
            ranking_equal += 1
        else:
            differing = [
                doc
                for doc, rank_a in enumerate(metrics_a["ranking"])
                if rank_a != metrics_b["ranking"][doc]
            ]
            ranking_disagreements.append(
                {
                    "query_id": key[0],
                    "repetition": key[1],
                    "pass_index": key[2],
                    "first_differing_positions": differing[:5],
                }
            )
    return {
        "n_paired_passes": len(shared),
        "max_abs_score_delta": max_delta,
        "ranking_equal_passes": ranking_equal,
        "ranking_disagreements": ranking_disagreements,
        "ranking_equality_fraction": (ranking_equal / len(shared) if shared else None),
    }


def h1_device_parity(records: list[dict[str, Any]]) -> dict[str, Any]:
    rows_cpu = _measured_rows(_complete_reps(records, "torch_cpu"))
    rows_mps = _measured_rows(_complete_reps(records, "torch_mps"))
    if not rows_cpu or not rows_mps:
        return {
            "hypothesis": "H1",
            "status": "not_evaluable",
            "reason": "torch_cpu and torch_mps need complete repetitions",
        }
    parity = _max_abs_delta_and_rankings(rows_cpu, rows_mps)
    gate = (
        parity["ranking_equality_fraction"] == 1.0
        and parity["max_abs_score_delta"] <= SCORE_TOLERANCE
    )
    return {
        "hypothesis": "H1",
        "tolerance": SCORE_TOLERANCE,
        **parity,
        "gate_pass": gate,
    }


def h2_mps_speed(records: list[dict[str, Any]]) -> dict[str, Any]:
    from experiments._lib import stats as stats_lib

    lat_cpu = [
        value
        for values in _latencies_by_query(
            _measured_rows(_complete_reps(records, "torch_cpu"))
        ).values()
        for value in values
    ]
    lat_mps = [
        value
        for values in _latencies_by_query(
            _measured_rows(_complete_reps(records, "torch_mps"))
        ).values()
        for value in values
    ]
    if not lat_cpu or not lat_mps:
        return {
            "hypothesis": "H2",
            "status": "not_evaluable",
            "reason": "torch_cpu and torch_mps need complete repetitions",
        }
    median_cpu = _median(lat_cpu)
    median_mps = _median(lat_mps)
    ratio = median_mps / median_cpu if median_cpu else None
    boot = stats_lib.paired_bootstrap_ci(
        lat_mps[: len(lat_cpu)],
        lat_cpu[: len(lat_cpu)],
        seed=harness.SUMMARY_SEED,
    )
    return {
        "hypothesis": "H2",
        "median_latency_ms_torch_cpu": median_cpu,
        "median_latency_ms_torch_mps": median_mps,
        "ratio": ratio,
        "ratio_gate": MPS_SPEED_RATIO_GATE,
        "paired_bootstrap": boot,
        "gate_pass": ratio is not None and ratio <= MPS_SPEED_RATIO_GATE,
    }


def _manifest_numbers(reps: list[dict[str, Any]]) -> dict[str, Any]:
    """Cold start / peak RSS averaged over complete repetitions."""
    cold_starts: list[float] = []
    peak_rss: list[int] = []
    for rep in reps:
        manifest = rep.get("manifest") or {}
        if manifest.get("cold_start_s") is not None:
            cold_starts.append(float(manifest["cold_start_s"]))
        if manifest.get("peak_rss_bytes") is not None:
            peak_rss.append(int(manifest["peak_rss_bytes"]))
    return {
        "cold_start_s_mean": (sum(cold_starts) / len(cold_starts)) if cold_starts else None,
        "peak_rss_bytes_max": max(peak_rss) if peak_rss else None,
    }


def h3_operational_bound(records: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = _manifest_numbers(_complete_reps(records, "onnx_cpu"))
    mps = _manifest_numbers(_complete_reps(records, "torch_mps"))
    if baseline["peak_rss_bytes_max"] is None or mps["peak_rss_bytes_max"] is None:
        return {
            "hypothesis": "H3",
            "status": "not_evaluable",
            "reason": "onnx_cpu and torch_mps need complete repetitions",
        }
    rss_ratio = mps["peak_rss_bytes_max"] / baseline["peak_rss_bytes_max"]
    cold_ratio = None
    if baseline["cold_start_s_mean"] and mps["cold_start_s_mean"]:
        cold_ratio = mps["cold_start_s_mean"] / baseline["cold_start_s_mean"]
    gate = rss_ratio <= RSS_RATIO_GATE and (
        cold_ratio is None or cold_ratio <= COLD_START_RATIO_GATE
    )
    return {
        "hypothesis": "H3",
        "baseline_onnx_cpu": baseline,
        "torch_mps": mps,
        "rss_ratio": rss_ratio,
        "rss_ratio_gate": RSS_RATIO_GATE,
        "cold_start_ratio": cold_ratio,
        "cold_start_ratio_gate": COLD_START_RATIO_GATE,
        "gate_pass": gate,
    }


def h4_backend_attribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    rows_onnx = _measured_rows(_complete_reps(records, "onnx_cpu"))
    rows_tcpu = _measured_rows(_complete_reps(records, "torch_cpu"))
    rows_mps = _measured_rows(_complete_reps(records, "torch_mps"))
    if not rows_onnx or not rows_tcpu:
        return {
            "hypothesis": "H4",
            "status": "not_evaluable",
            "reason": "onnx_cpu and torch_cpu need complete repetitions",
        }
    onnx_vs_tcpu = _max_abs_delta_and_rankings(rows_onnx, rows_tcpu)
    device_parity_available = bool(rows_mps)
    # Protocol section 19: an ONNX-vs-Torch disagreement is classified as
    # backend/precision divergence only when the same pass does NOT also
    # disagree between torch_cpu and torch_mps (B vs C cross-check).
    device_disagree_keys: set[tuple[str, int, int]] = set()
    if device_parity_available:
        device_parity = _max_abs_delta_and_rankings(rows_tcpu, rows_mps)
        device_disagree_keys = {
            (d["query_id"], d["repetition"], d["pass_index"])
            for d in device_parity["ranking_disagreements"]
        }
    attributed = []
    for disagreement in onnx_vs_tcpu["ranking_disagreements"]:
        key = (
            disagreement["query_id"],
            disagreement["repetition"],
            disagreement["pass_index"],
        )
        if not device_parity_available:
            classification = "unattributed_missing_mps_cell"
        elif key in device_disagree_keys:
            classification = "overlaps_device_divergence"
        else:
            classification = "backend_or_precision_divergence"
        attributed.append({**disagreement, "classification": classification})
    return {
        "hypothesis": "H4",
        "onnx_vs_torch_cpu": onnx_vs_tcpu,
        "device_parity_cell_available": device_parity_available,
        "attributed_disagreements": attributed,
    }


def h5_manifest_truth(result: dict[str, Any]) -> dict[str, Any]:
    records = _repetition_records(result)
    checked: list[dict[str, Any]] = []
    all_valid = True
    for rep in records:
        if rep.get("status") != "complete":
            continue
        manifest = rep.get("manifest") or {}
        providers = manifest.get("onnx_effective_providers")
        device = manifest.get("torch_effective_device")
        proved = bool(providers or device)
        checked.append(
            {
                "cell_id": rep.get("cell_id"),
                "repetition": rep.get("repetition"),
                "onnx_effective_providers": providers,
                "torch_effective_device": device,
                "proved_before_timing": proved,
            }
        )
        all_valid = all_valid and proved
    return {
        "hypothesis": "H5",
        "checked_repetitions": checked,
        "gate_pass": all_valid and bool(checked),
    }


def summarise(result: dict[str, Any]) -> dict[str, Any]:
    """Assemble the full H1-H5 summary over complete cells only."""
    records = _repetition_records(result)
    return {
        "experiment_id": result.get("experiment_id"),
        "protocol_version": result.get("protocol_version"),
        "workload_identity": result.get("workload_identity"),
        "cell_statuses": result.get("cells", []),
        "hypotheses": {
            "H1_device_parity": h1_device_parity(records),
            "H2_mps_speed": h2_mps_speed(records),
            "H3_operational_bound": h3_operational_bound(records),
            "H4_backend_attribution": h4_backend_attribution(records),
            "H5_manifest_truth": h5_manifest_truth(result),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SCRIPT_DIR / "output",
        help="directory holding eval_results.json",
    )
    args = parser.parse_args()

    results_path = args.output_dir / "eval_results.json"
    if not results_path.exists():
        print(
            f"no results to summarise: {results_path} is absent (run run_eval.py first)",
            file=sys.stderr,
        )
        return 1
    result = json.loads(results_path.read_text(encoding="utf-8"))
    summary = summarise(result)
    harness.write_json_atomic(args.output_dir / "eval_results.summary.json", summary)
    print(json.dumps(summary["hypotheses"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
