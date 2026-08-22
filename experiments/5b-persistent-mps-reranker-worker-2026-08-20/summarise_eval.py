"""Gate adjudication and evidence views for Experiment 5b (protocol §10/§16).

Reads the frozen campaign artefacts (raw rows, memory samples, probe rows,
checkpoint), adjudicates G1–G9 against the pre-registered decision rules and
writes ``eval_results.json``, ``eval_results.summary.json`` and the canonical
correctness projection twice with a byte-identity assertion (D9).

Pure stdlib plus ``stats_extras``; no Torch import, no model, no network.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import artefacts as art
import harness
import protocol_frames as pf
import stats_extras as se

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

W1 = "onnx_cpu_in_process"
W2 = "torch_mps_fresh"
W3 = "torch_mps_persistent"
W4 = "torch_cpu_persistent"
W5 = "torch_cpu_fresh"
PERSISTENT_CELLS = (W3, W4)
ALL_CELLS = (W1, W2, W3, W4, W5)

BOOTSTRAP_SEED = 20260821
BLOCK_LENGTH = 40
N_RESAMPLES = 1000
G1_TOLERANCE = 1e-4
SPEED_RATIO_MAX = 0.8
FLOAT_EPS = 1e-9  # binary-float boundary guard (0.7 + 0.9) / 2 vs 0.8
G4_REQUESTS_MAX = 150
G5_WORKER_PLATEAU_MIB = 750.0
G5_TREE_PLATEAU_MIB = 1250.0
G5_TREE_PEAK_MIB = 1500.0
G6_MIB_PER_1000_MAX = 20.0
PLATEAU_START, PLATEAU_END = 801, 1000
GROWTH_START, GROWTH_END = 201, 1000
G7_REQUIRED = ("worker-death", "worker-hang", "request-deadline", "stdout-backpressure")
G8_REQUIRED = (
    "orderly-shutdown",
    "eof-stdin",
    "idle-expiry-restart",
    "parent-death-idle",
    "parent-death-inflight",
)

OK_VERDICT = "PASS"
FAILED_VERDICT = "FAIL"
NOT_EVALUABLE_VERDICT = "NOT_EVALUABLE"


def _admitted_primary(rows: list[dict[str, Any]], cell_id: str) -> dict[tuple[int, int], dict]:
    """Admitted, measured, primary rows for one cell keyed by (block, request)."""
    selected: dict[tuple[int, int], dict] = {}
    for row in rows:
        if row.get("cell_id") != cell_id:
            continue
        if row.get("phase") != "measured" or row.get("source") != "primary":
            continue
        metrics = row.get("metrics", {})
        if metrics.get("admitted") is not True:
            continue
        selected[(int(row["block"]), int(row["request_index"]))] = row
    return selected


def _gate(gate_id: str, verdict: str, numbers: dict[str, Any]) -> dict[str, Any]:
    return {"id": gate_id, "verdict": verdict, "numbers": numbers}


# ── G1: compatible-route correctness ──────────────────────────────────


def _compatible_parity(rows: list[dict[str, Any]], control: str, gate_id: str) -> dict[str, Any]:
    """Ranking equality and score delta between W3 and a Torch control."""
    treatment = _admitted_primary(rows, W3)
    control_rows = _admitted_primary(rows, control)
    keys = sorted(set(treatment) & set(control_rows))
    if not keys:
        return _gate(
            gate_id,
            NOT_EVALUABLE_VERDICT,
            {"ranking_equality_fraction": None, "max_abs_score_delta": None, "pairs": 0},
        )
    equal = 0
    max_delta = 0.0
    for key in keys:
        treatment_metrics = treatment[key]["metrics"]
        control_metrics = control_rows[key]["metrics"]
        if se.rankings_equal(treatment_metrics["ranking"], control_metrics["ranking"]):
            equal += 1
        max_delta = max(
            max_delta,
            se.paired_max_abs_delta(treatment_metrics["scores"], control_metrics["scores"]),
        )
    fraction = equal / len(keys)
    verdict = OK_VERDICT if fraction == 1.0 and max_delta <= G1_TOLERANCE else FAILED_VERDICT
    return _gate(
        gate_id,
        verdict,
        {
            "ranking_equality_fraction": fraction,
            "max_abs_score_delta": float(max_delta),
            "pairs": len(keys),
        },
    )


def g1a(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """W3 versus paired W2 Torch-MPS responses."""
    return _compatible_parity(rows, W2, "G1a")


def g1b(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """W3 versus paired W4 Torch-CPU persistent responses."""
    return _compatible_parity(rows, W4, "G1b")


def g1c(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Every admitted response must prove route and reranking."""
    violations = 0
    warmup_violations = 0
    for row in rows:
        metrics = row.get("metrics", {})
        flags = (
            metrics.get("route_ok"),
            metrics.get("rerank_ok"),
            metrics.get("cardinality_ok"),
            metrics.get("generation_ok"),
            metrics.get("admitted"),
        )
        if any(flag is False for flag in flags):
            violations += 1
            if row.get("phase") == "warmup":
                warmup_violations += 1
    return _gate(
        "G1c",
        OK_VERDICT if violations == 0 else FAILED_VERDICT,
        {"violations": violations, "warmup_violations": warmup_violations},
    )


# ── G2/G3: parent-observed speed ──────────────────────────────────────


def _speed_gate(
    rows: list[dict[str, Any]],
    control: str,
    gate_id: str,
    interpretation: str | None = None,
) -> dict[str, Any]:
    """Median of per-block median-latency ratios; PASS at or below 0.8."""
    treatment = _admitted_primary(rows, W3)
    control_rows = _admitted_primary(rows, control)
    blocks = sorted({block for block, _ in treatment} & {block for block, _ in control_rows})
    if not blocks:
        return _gate(
            gate_id,
            NOT_EVALUABLE_VERDICT,
            {"per_block_ratios": {}, "median_ratio": None, "threshold": SPEED_RATIO_MAX},
        )
    ratios: dict[str, float] = {}
    for block in blocks:
        t_values = [
            row["latency_ms"] for (block_id, _), row in treatment.items() if block_id == block
        ]
        c_values = [
            row["latency_ms"] for (block_id, _), row in control_rows.items() if block_id == block
        ]
        if not t_values or not c_values:
            continue
        ratios[str(block)] = statistics.median(t_values) / statistics.median(c_values)
    if not ratios:
        return _gate(
            gate_id,
            NOT_EVALUABLE_VERDICT,
            {"per_block_ratios": {}, "median_ratio": None, "threshold": SPEED_RATIO_MAX},
        )
    gate_value = statistics.median(list(ratios.values()))
    verdict = OK_VERDICT if gate_value <= SPEED_RATIO_MAX + FLOAT_EPS else FAILED_VERDICT
    numbers: dict[str, Any] = {
        "per_block_ratios": ratios,
        "median_ratio": gate_value,
        "threshold": SPEED_RATIO_MAX,
    }
    if interpretation:
        numbers["interpretation"] = interpretation
    return _gate(gate_id, verdict, numbers)


def g2(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """W3 versus W4: the device-speed gate."""
    return _speed_gate(rows, W4, "G2")


def g3(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """W3 versus W1: the deployment-value gate (not an H2 replication)."""
    return _speed_gate(
        rows,
        W1,
        "G3",
        interpretation=(
            "deployment comparison only; not a cross-backend correctness gate "
            "or Experiment 5 H2 replication"
        ),
    )


# ── G4: cumulative startup break-even ─────────────────────────────────


def _ordered_latencies(
    selected: dict[tuple[int, int], dict], block: int
) -> tuple[list[int], list[float]]:
    items = sorted(
        (request, row["latency_ms"])
        for (block_id, request), row in selected.items()
        if block_id == block
    )
    return [request for request, _ in items], [latency for _, latency in items]


def g4(checkpoint: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Cumulative break-even versus paired W1 with a bootstrap bound."""
    treatment = _admitted_primary(rows, W3)
    baseline = _admitted_primary(rows, W1)
    per_block: dict[str, Any] = {}
    bounds: list[float] = []
    n_stars: list[float] = []
    horizon = 0
    for key, record in sorted(checkpoint.get("records", {}).items()):
        if not key.startswith(W3 + "__block") or record.get("status") != "complete":
            continue
        block = int(key.rsplit("block", 1)[1])
        if "startup_s" not in record or "warmup_s" not in record:
            continue
        fixed_ms = (float(record["startup_s"]) + float(record["warmup_s"])) * 1000.0
        w3_requests, w3_latencies = _ordered_latencies(treatment, block)
        w1_requests, w1_latencies = _ordered_latencies(baseline, block)
        if not w3_latencies or not w1_latencies or w3_requests != w1_requests:
            continue
        horizon = max(horizon, len(w3_latencies))

        def stat_fn(
            xs: Sequence[float],
            ys: Sequence[float],
            *,
            _fixed_ms: float = fixed_ms,
        ) -> float:
            persistent_cum: list[float] = []
            baseline_cum: list[float] = []
            p_total = _fixed_ms
            b_total = 0.0
            for x_value, y_value in zip(xs, ys, strict=True):
                p_total += x_value
                b_total += y_value
                persistent_cum.append(p_total)
                baseline_cum.append(b_total)
            return se.first_sustained_crossover(persistent_cum, baseline_cum)

        n_star = stat_fn(w3_latencies, w1_latencies)
        bootstrap = se.block_bootstrap_stat_upper_bound(
            stat_fn,
            w3_latencies,
            w1_latencies,
            seed=BOOTSTRAP_SEED,
            block_length=BLOCK_LENGTH,
            n_resamples=N_RESAMPLES,
        )
        n_stars.append(n_star)
        bounds.append(float(bootstrap["upper_bound"]))
        per_block[str(block)] = {
            "n_star": None if n_star == float("inf") else n_star,
            "never_crossed": n_star == float("inf"),
            "bootstrap_upper_bound": (
                None if bootstrap["upper_bound"] == float("inf") else bootstrap["upper_bound"]
            ),
        }
    if not per_block:
        return _gate(
            "G4",
            NOT_EVALUABLE_VERDICT,
            {"per_block": {}, "upper_bound": None, "horizon": horizon},
        )
    upper_bound = max(bounds)
    verdict = OK_VERDICT if upper_bound <= G4_REQUESTS_MAX else FAILED_VERDICT
    return _gate(
        "G4",
        verdict,
        {
            "per_block": per_block,
            "median_n_star": (
                None if any(n == float("inf") for n in n_stars) else statistics.median(n_stars)
            ),
            "upper_bound": None if upper_bound == float("inf") else upper_bound,
            "requests_max": G4_REQUESTS_MAX,
            "horizon": horizon,
        },
    )


# ── G5/G6: memory ceilings and growth ─────────────────────────────────


def _memory_groups(
    samples: list[dict[str, Any]], cells: tuple[str, ...]
) -> dict[tuple[str, int, int], list[dict[str, Any]]]:
    groups: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        if sample.get("cell_id") in cells:
            groups[(str(sample["cell_id"]), int(sample["block"]), int(sample["lifetime"]))].append(
                sample
            )
    return groups


def g5(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-lifetime worker/tree plateau and tree peak versus the D5 ceilings."""
    groups = _memory_groups(samples, (W3,))
    if not groups:
        return _gate("G5", NOT_EVALUABLE_VERDICT, {"lifetimes": {}, "ceilings": {}})
    lifetimes: dict[str, Any] = {}
    verdict = OK_VERDICT
    for (cell, block, lifetime), rows in sorted(groups.items()):
        window = [row for row in rows if PLATEAU_START <= int(row["request_index"]) <= PLATEAU_END]
        key = f"{cell}__block{block}__lifetime{lifetime}"
        if not window:
            lifetimes[key] = {"status": "no plateau window samples"}
            verdict = NOT_EVALUABLE_VERDICT
            continue
        worker_plateau = se.percentile(
            [float(row["worker_rss_bytes"]) / 1048576.0 for row in window], 0.95
        )
        tree_plateau = se.percentile(
            [float(row["tree_rss_bytes"]) / 1048576.0 for row in window], 0.95
        )
        tree_peak = max(float(row["tree_rss_bytes"]) for row in rows) / 1048576.0
        lifetime_pass = (
            worker_plateau <= G5_WORKER_PLATEAU_MIB
            and tree_plateau <= G5_TREE_PLATEAU_MIB
            and tree_peak <= G5_TREE_PEAK_MIB
        )
        lifetimes[key] = {
            "worker_plateau_rss_mib": worker_plateau,
            "tree_plateau_rss_mib": tree_plateau,
            "tree_peak_rss_mib": tree_peak,
            "pass": lifetime_pass,
        }
        if not lifetime_pass:
            verdict = FAILED_VERDICT
    return _gate(
        "G5",
        verdict,
        {
            "lifetimes": lifetimes,
            "ceilings": {
                "worker_plateau_rss_mib_max": G5_WORKER_PLATEAU_MIB,
                "tree_plateau_rss_mib_max": G5_TREE_PLATEAU_MIB,
                "tree_peak_rss_mib_max": G5_TREE_PEAK_MIB,
            },
        },
    )


def _slope_block_bootstrap(
    series_by_group: list[tuple[list[float], list[float]]],
    *,
    seed: int,
    block_length: int,
    n_resamples: int,
    confidence: float,
) -> dict[str, float | int]:
    """Pooled slope bootstrap: blocks never cross lifetimes (D8).

    Each resample draws blocks within every group independently and
    concatenates them before recomputing the slope.
    """
    rng = random.Random(seed)  # noqa: S311 — seeded determinism is contractual
    slopes: list[float] = []

    def pooled_slope(resampled: list[tuple[list[float], list[float]]]) -> float:
        xs: list[float] = []
        ys: list[float] = []
        for x_part, y_part in resampled:
            xs.extend(x_part)
            ys.extend(y_part)
        return se.theilsen_slope(xs, ys)

    for _ in range(n_resamples):
        parts: list[tuple[list[float], list[float]]] = []
        for xs, ys in series_by_group:
            n = len(xs)
            starts = list(range(0, n, block_length))
            indices: list[int] = []
            while len(indices) < n:
                start = rng.choice(starts)
                indices.extend(range(start, min(start + block_length, n)))
            indices = indices[:n]
            parts.append(([xs[i] for i in indices], [ys[i] for i in indices]))
        slopes.append(pooled_slope(parts))
    return {
        "slope": pooled_slope(series_by_group),
        "upper_bound": se.percentile(slopes, confidence),
        "n_resamples": n_resamples,
        "confidence": confidence,
    }


def g6(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Theil-Sen growth with per-lifetime and pooled bootstrap bounds (< 20)."""
    groups = _memory_groups(samples, PERSISTENT_CELLS)
    if not groups:
        return _gate("G6", NOT_EVALUABLE_VERDICT, {"lifetimes": {}, "pooled": None})
    lifetimes: dict[str, Any] = {}
    series: list[tuple[list[float], list[float]]] = []
    verdict = OK_VERDICT
    for (cell, block, lifetime), rows in sorted(groups.items()):
        window = sorted(
            (row for row in rows if GROWTH_START <= int(row["request_index"]) <= GROWTH_END),
            key=lambda row: (int(row["request_index"]), float(row["t_monotonic"])),
        )
        key = f"{cell}__block{block}__lifetime{lifetime}"
        if not window:
            lifetimes[key] = {"status": "no growth window samples"}
            verdict = NOT_EVALUABLE_VERDICT
            continue
        requests = [float(row["request_index"]) for row in window]
        rss_mib = [float(row["worker_rss_bytes"]) / 1048576.0 for row in window]
        slope = se.theilsen_slope(requests, rss_mib) * 1000.0
        bound = (
            se.block_bootstrap_slope_upper_bound(
                requests,
                rss_mib,
                seed=BOOTSTRAP_SEED,
                block_length=BLOCK_LENGTH,
                n_resamples=N_RESAMPLES,
            )["upper_bound"]
            * 1000.0
        )
        lifetimes[key] = {
            "slope_mib_per_1000_requests": slope,
            "upper_bound_mib_per_1000_requests": bound,
        }
        if not bound < G6_MIB_PER_1000_MAX:
            verdict = FAILED_VERDICT
        series.append((requests, rss_mib))
    pooled = _slope_block_bootstrap(
        series,
        seed=BOOTSTRAP_SEED,
        block_length=BLOCK_LENGTH,
        n_resamples=N_RESAMPLES,
        confidence=0.95,
    )
    pooled_bound = float(pooled["upper_bound"]) * 1000.0
    if not pooled_bound < G6_MIB_PER_1000_MAX:
        verdict = FAILED_VERDICT
    return _gate(
        "G6",
        verdict,
        {
            "lifetimes": lifetimes,
            "pooled": {
                "slope_mib_per_1000_requests": float(pooled["slope"]) * 1000.0,
                "upper_bound_mib_per_1000_requests": pooled_bound,
            },
            "bound_mib_per_1000_requests_strictly_below": G6_MIB_PER_1000_MAX,
        },
    )


# ── G7/G8: lifecycle probes ───────────────────────────────────────────


def _probe_gate(
    probe_rows: list[dict[str, Any]], required: tuple[str, ...], gate_id: str
) -> dict[str, Any]:
    outcomes: dict[str, list[str]] = defaultdict(list)
    for row in probe_rows:
        outcomes[str(row.get("probe"))].append(str(row.get("outcome")))
    missing = [name for name in required if "pass" not in outcomes.get(name, [])]
    failures = {
        name: [outcome for outcome in results if outcome == "fail"]
        for name, results in outcomes.items()
        if "fail" in results
    }
    numbers: dict[str, Any] = {
        "required": list(required),
        "observed": {name: results for name, results in sorted(outcomes.items())},
        "missing_pass": missing,
        "failing": sorted(failures),
    }
    verdict = OK_VERDICT if not missing and not failures else FAILED_VERDICT
    return _gate(gate_id, verdict, numbers)


def g7(probe_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Deadline-bounded failure fallback probes."""
    return _probe_gate(probe_rows, G7_REQUIRED, "G7")


def g8(probe_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Shutdown, EOF, idle-expiry and parent-death orphan freedom."""
    gate = _probe_gate(probe_rows, G8_REQUIRED, "G8")
    orphans = [
        str(row.get("probe"))
        for row in probe_rows
        if row.get("outcome") == "pass" and row.get("orphans_remaining") not in (None, 0)
    ]
    gate["numbers"]["orphan_leaks_on_passing_rows"] = orphans
    if orphans:
        gate["verdict"] = FAILED_VERDICT
    return gate


# ── descriptive views ─────────────────────────────────────────────────


def onnx_torch_divergence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive W3-versus-W1 divergence; explicitly excluded from G1."""
    treatment = _admitted_primary(rows, W3)
    baseline = _admitted_primary(rows, W1)
    keys = sorted(set(treatment) & set(baseline))
    equal = 0
    max_delta = 0.0
    flips = 0
    for key in keys:
        t_metrics = treatment[key]["metrics"]
        b_metrics = baseline[key]["metrics"]
        if se.rankings_equal(t_metrics["ranking"], b_metrics["ranking"]):
            equal += 1
        for doc_id, t_score in t_metrics["scores"].items():
            b_score = b_metrics["scores"].get(doc_id)
            if b_score is None:
                continue
            max_delta = max(max_delta, abs(float(t_score) - float(b_score)))
            if (float(t_score) < 0.5 <= float(b_score)) or (float(b_score) < 0.5 <= float(t_score)):
                flips += 1
    return {
        "classification": ("descriptive backend/quantisation divergence; excluded from G1"),
        "pairs": len(keys),
        "ranking_equality_fraction": (equal / len(keys)) if keys else None,
        "max_abs_score_delta": max_delta if keys else None,
        "threshold_decision_flips_at_0p5": flips,
    }


def memory_ratio_view(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Absolute MiB memory view plus ratios to the paired W1 parent state."""
    w1_parent = [
        float(row["parent_rss_bytes"]) / 1048576.0 for row in samples if row.get("cell_id") == W1
    ]
    w1_plateau = se.percentile(w1_parent, 0.95) if w1_parent else None
    g5_numbers = g5(samples)["numbers"]
    view: dict[str, Any] = {"w1_parent_plateau_rss_mib": w1_plateau}
    for key, lifetime in g5_numbers.get("lifetimes", {}).items():
        if not isinstance(lifetime, dict) or "worker_plateau_rss_mib" not in lifetime:
            continue
        view[key] = {
            **lifetime,
            "worker_to_w1_ratio": (
                lifetime["worker_plateau_rss_mib"] / w1_plateau if w1_plateau else None
            ),
            "tree_to_w1_ratio": (
                lifetime["tree_plateau_rss_mib"] / w1_plateau if w1_plateau else None
            ),
        }
    return view


def latency_view(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-cell median/P95 parent-observed latency plus paired ratios."""
    view: dict[str, Any] = {}
    for cell in ALL_CELLS:
        selected = _admitted_primary(rows, cell)
        values = [row["latency_ms"] for row in selected.values()]
        if values:
            view[cell] = {
                "n": len(values),
                "median_ms": statistics.median(values),
                "p95_ms": se.percentile(values, 0.95),
            }
    return view


def correctness_projection(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Canonical correctness projection: rankings and scores only (D9)."""
    pairs: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("phase") != "measured" or row.get("source") != "primary":
            continue
        if row.get("metrics", {}).get("admitted") is not True:
            continue
        key = f"{row['block']}:{row['request_index']}:{row['cell_id']}"
        pairs[key] = {
            "ranking": list(row["metrics"]["ranking"]),
            "scores": {doc: float(score) for doc, score in row["metrics"]["scores"].items()},
        }
    return {"pairs": dict(sorted(pairs.items()))}


# ── artefact loading and the G9 admissibility gate ────────────────────
def _read_unit_files(directory: Path, kind: str) -> list[dict[str, Any]]:
    """Merge per-unit artefact files (raw rows / memory samples).

    The runner writes one file per complete lifetime unit under
    ``<kind>/<cell>__block<N>.jsonl`` so an interrupted unit restarts from
    request zero without polluting other units' evidence.
    """
    rows: list[dict[str, Any]] = []
    unit_dir = directory / kind
    if unit_dir.is_dir():
        for path in sorted(unit_dir.glob("*.jsonl")):
            rows.extend(pf.read_jsonl(path))
    return rows


def _unit_of_row(row: dict[str, Any]) -> str:
    """Checkpoint unit key for a row (cell + block)."""
    return f"{row['cell_id']}__block{row['block']}"


def load_rows(output_dir: str | Path) -> dict[str, Any]:
    """Load the frozen artefacts; missing files degrade explicitly.

    Prefers the runner's per-unit files; a legacy single ``raw_rows.jsonl``
    is still honoured.  Rows are filtered to checkpoint-complete units so
    partial lifetimes remain evidence without entering aggregates (D16).
    """
    directory = Path(output_dir)
    checkpoint_path = directory / "eval_results_checkpoint.json"
    checkpoint = (
        json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else {}
    )
    completed = set(checkpoint.get("completed", []))
    legacy_rows = (
        pf.read_jsonl(directory / "raw_rows.jsonl")
        if (directory / "raw_rows.jsonl").exists()
        else []
    )
    raw_rows = _read_unit_files(directory, "raw_rows") or legacy_rows
    memory_samples = _read_unit_files(directory, "memory_samples")
    if (directory / "memory_samples.jsonl").exists() and not memory_samples:
        memory_samples = pf.read_jsonl(directory / "memory_samples.jsonl")
    if completed:
        raw_rows = [row for row in raw_rows if _unit_of_row(row) in completed]
        memory_samples = [sample for sample in memory_samples if _unit_of_row(sample) in completed]
    probe_path = directory / "lifecycle_probes.jsonl"
    probe_rows = pf.read_jsonl(probe_path) if probe_path.exists() else []
    return {
        "raw_rows": raw_rows,
        "memory_samples": memory_samples,
        "probe_rows": probe_rows,
        "checkpoint": checkpoint,
    }


def g9(context: dict[str, Any]) -> dict[str, Any]:
    """TDR-014 admissibility: plan agreement, preflight, rows, statuses."""
    reasons: list[str] = []
    preflight = context.get("preflight_summary") or {}
    if not preflight.get("plan_agreement"):
        reasons.append("plan agreement not recorded green")
    if not preflight.get("all_green"):
        reasons.append("preflight not green")
    checkpoint = context.get("checkpoint") or {}
    records = checkpoint.get("records", {})
    if not records:
        reasons.append("checkpoint has no lifetime records")
    incomplete = [key for key, record in records.items() if record.get("status") != "complete"]
    if incomplete:
        reasons.append(f"incomplete checkpoint units: {sorted(incomplete)[:5]}")
    if not context.get("raw_rows"):
        reasons.append("no raw per-request rows")
    else:
        try:
            from experiments._lib import stats as stats_lib

            stats_lib.validate_per_query_rows(context["raw_rows"])
        except Exception as exc:  # noqa: BLE001 — evidence of contract breach
            reasons.append(f"raw rows violate the D16 contract: {exc}")
    if not context.get("projection_byte_identical"):
        reasons.append("correctness projection not byte-identical across runs")
    verdict = OK_VERDICT if not reasons else FAILED_VERDICT
    return _gate("G9", verdict, {"reasons": reasons})


# ── assembly and CLI ──────────────────────────────────────────────────


def summarise(output_dir: str | Path) -> dict[str, Any]:
    """Adjudicate every gate and assemble the summary payload."""
    loaded = load_rows(output_dir)
    rows = loaded["raw_rows"]
    samples = loaded["memory_samples"]
    probe_rows = loaded["probe_rows"]
    checkpoint = loaded["checkpoint"]

    projection_a = correctness_projection(rows)
    projection_b = correctness_projection(rows)
    projection_bytes_a = json.dumps(projection_a, sort_keys=True, separators=(",", ":"))
    projection_bytes_b = json.dumps(projection_b, sort_keys=True, separators=(",", ":"))
    byte_identical = projection_bytes_a == projection_bytes_b

    preflight_path = Path(output_dir) / "preflight" / "_summary.json"
    preflight_summary = (
        json.loads(preflight_path.read_text(encoding="utf-8")) if preflight_path.exists() else {}
    )
    context = {
        "preflight_summary": preflight_summary,
        "checkpoint": checkpoint,
        "raw_rows": rows,
        "projection_byte_identical": byte_identical,
    }
    gates = [
        g1a(rows),
        g1b(rows),
        g1c(rows),
        g2(rows),
        g3(rows),
        g4(checkpoint, rows),
        g5(samples),
        g6(samples),
        g7(probe_rows),
        g8(probe_rows),
        g9(context),
    ]
    verdicts = {gate["verdict"] for gate in gates}
    overall = (
        NOT_EVALUABLE_VERDICT
        if NOT_EVALUABLE_VERDICT in verdicts
        else (OK_VERDICT if verdicts == {OK_VERDICT} else FAILED_VERDICT)
    )
    return {
        "experiment_id": "5b-persistent-mps-reranker-worker",
        # Report the live protocol version (harness constant) rather than a
        # stale literal; v1.0 output mislabelled the v1.1 campaign evidence.
        "protocol_version": harness.PROTOCOL_VERSION,
        "gates": gates,
        "overall_verdict": overall,
        "promotion_note": (
            "any NOT_EVALUABLE or FAIL gate rejects promotion; ONNX CPU stays "
            "the production default"
            if overall != OK_VERDICT
            else "all gates passed; a separate production-worker OpenSpec and "
            "decision record is required before any production worker"
        ),
        "views": {
            "latency": latency_view(rows),
            "memory_ratio": memory_ratio_view(samples),
            "onnx_torch_divergence": onnx_torch_divergence(rows),
        },
        "projection_sha256": __import__("hashlib")
        .sha256(projection_bytes_a.encode("utf-8"))
        .hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    summary = summarise(output_dir)

    loaded = load_rows(output_dir)
    projection = correctness_projection(loaded["raw_rows"])
    projection_text = json.dumps(projection, sort_keys=True, separators=(",", ":"))
    run1 = output_dir / "correctness_projection_run1.json"
    run2 = output_dir / "correctness_projection_run2.json"
    run1.write_text(projection_text + "\n", encoding="utf-8")
    run2.write_text(projection_text + "\n", encoding="utf-8")
    if run1.read_bytes() != run2.read_bytes():
        raise SystemExit("correctness projection runs differ: never ship this")

    art.write_json_atomic(output_dir / "eval_results.json", summary)
    art.write_json_atomic(output_dir / "eval_results.summary.json", summary)

    for gate in summary["gates"]:
        print(f"{gate['id']}: {gate['verdict']}")
    print(f"overall: {summary['overall_verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
