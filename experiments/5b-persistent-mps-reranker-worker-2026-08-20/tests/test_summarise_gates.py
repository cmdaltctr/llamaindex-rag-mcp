"""Fast tests for summarise_eval gates (OpenSpec task 4.1) — RED until implemented.

Synthesises tiny raw-row, memory-sample, probe-row and checkpoint fixtures
with the artefacts builders and adjudicates every gate function: G1a/G1b
ranking parity, G1c admission truth, G2/G3 latency ratios (including the
0.8 boundary), G4 cumulative break-even, G5 per-lifetime memory ceilings,
G6 strict growth bound, G7/G8 probe batteries, load_rows, and the canonical
correctness projection.  No model, no network; every fixture is in-memory
or in a tmp directory.
"""

from __future__ import annotations

import json

import artefacts as art
from _lazy_module import LazyModule

sm = LazyModule("summarise_eval")  # RED (ModuleNotFoundError) until implemented

VERDICTS = {"PASS", "FAIL", "NOT_EVALUABLE"}

W1 = "onnx_cpu_in_process"
W2 = "torch_mps_fresh"
W3 = "torch_mps_persistent"
W4 = "torch_cpu_persistent"

MIB = 1048576


# ── fixtures ──────────────────────────────────────────────────────────


def raw_row(
    cell: str,
    block: int,
    req: int,
    lat: float,
    ranking: list[str],
    scores: dict,
    *,
    lifetime: int = 1,
    admitted: bool = True,
    route_ok: bool = True,
    rerank_ok: bool = True,
    cardinality_ok: bool = True,
    generation_ok: bool = True,
    phase: str = "measured",
    source: str = "primary",
    worker_pid: int = 4321,
    reason: str | None = None,
) -> dict:
    metrics = {
        "scores": dict(scores),
        "ranking": list(ranking),
        "route_ok": route_ok,
        "rerank_ok": rerank_ok,
        "cardinality_ok": cardinality_ok,
        "generation_ok": generation_ok,
        "admitted": admitted,
    }
    if reason is not None:
        metrics["reason"] = reason
    return art.build_raw_row(
        cell_id=cell,
        block=block,
        lifetime=lifetime,
        request_index=req,
        query_id=f"pass0_q{req % 24:02d}",
        phase=phase,
        source=source,
        latency_ms=lat,
        generation=0,
        worker_pid=worker_pid,
        metrics=metrics,
    )


def mem_row(
    lifetime: int,
    req: int,
    worker_mib: float,
    parent_mib: float,
    tree_mib: float,
    *,
    cell: str = W3,
    block: int = 1,
) -> dict:
    return art.build_memory_sample(
        cell_id=cell,
        block=block,
        lifetime=lifetime,
        request_index=req,
        worker_rss_bytes=int(worker_mib * MIB),
        parent_rss_bytes=int(parent_mib * MIB),
        tree_rss_bytes=int(tree_mib * MIB),
    )


def probe_row(name: str, outcome: str) -> dict:
    return art.build_probe_row(
        probe=name,
        worker_pid=77,
        outcome=outcome,
        deadline_result="ok",
        detail="",
        generation=0,
    )


def paired_parity_rows(control_cell: str, *, swap: bool = False, delta: float = 0.0) -> list[dict]:
    rows = []
    for req in (1, 2, 3):
        ranking = ["a", "b"]
        treatment_scores = {"a": 0.9, "b": 0.4}
        control_scores = {"a": 0.9 - delta, "b": 0.4}
        rows.append(raw_row(W3, 1, req, 10.0, ranking, treatment_scores))
        control_ranking = ["b", "a"] if (swap and req == 2) else ranking
        rows.append(raw_row(control_cell, 1, req, 12.0, control_ranking, control_scores))
    return rows


def latency_rows(
    treatment_cell: str,
    control_cell: str,
    t_lat: float,
    c_lat: float,
    *,
    blocks=(1, 2),
    reqs=(1, 2, 3),
) -> list[dict]:
    rows = []
    for block in blocks:
        for req in reqs:
            rows.append(raw_row(treatment_cell, block, req, t_lat, ["a"], {"a": 0.5}))
            rows.append(raw_row(control_cell, block, req, c_lat, ["a"], {"a": 0.5}))
    return rows


def g4_fixture(startup_s: float, warmup_s: float, n: int = 60) -> tuple[dict, list[dict]]:
    rows = []
    for i in range(1, n + 1):
        rows.append(raw_row(W3, 1, i, 10.0, ["a"], {"a": 0.5}))
        rows.append(raw_row(W1, 1, i, 20.0, ["a"], {"a": 0.5}))
    key = art.checkpoint_key(W3, 1)
    checkpoint = art.build_checkpoint(
        experiment_id="5b-persistent-mps-reranker-worker",
        plan_sha256="00" * 32,
        completed=[key],
        records={key: {"status": "complete", "startup_s": startup_s, "warmup_s": warmup_s}},
    )
    return checkpoint, rows


def growth_samples(
    lifetime: int, cell: str, slope_mib_per_1000: float, *, block: int = 1
) -> list[dict]:
    rows = []
    for req in range(201, 1001, 10):
        offset = slope_mib_per_1000 * (req - 201) / 1000.0
        rows.append(
            mem_row(lifetime, req, 600.0 + offset, 300.0, 1000.0 + offset, cell=cell, block=block)
        )
    return rows


G7_PROBES = ("worker-death", "worker-hang", "request-deadline", "stdout-backpressure")
G8_PROBES = (
    "orderly-shutdown",
    "eof-stdin",
    "idle-expiry-restart",
    "parent-death-idle",
    "parent-death-inflight",
)


# ── G1a/G1b: compatible Torch parity ──────────────────────────────────


def test_g1a_pass_exact_parity() -> None:
    result = sm.g1a(paired_parity_rows(W2))
    assert result["verdict"] in VERDICTS
    assert result["verdict"] == "PASS"
    assert result["numbers"]["ranking_equality_fraction"] == 1.0
    assert result["numbers"]["max_abs_score_delta"] <= 1e-9
    assert result["numbers"]["pairs"] == 3


def test_g1a_fail_on_one_ranking_swap() -> None:
    result = sm.g1a(paired_parity_rows(W2, swap=True))
    assert result["verdict"] == "FAIL"
    assert result["numbers"]["ranking_equality_fraction"] < 1.0


def test_g1a_fail_on_score_delta_above_tolerance() -> None:
    result = sm.g1a(paired_parity_rows(W2, delta=2e-4))
    assert result["verdict"] == "FAIL"
    assert result["numbers"]["max_abs_score_delta"] > 1e-4


def test_g1a_pass_on_tiny_delta_within_tolerance() -> None:
    result = sm.g1a(paired_parity_rows(W2, delta=1e-9))
    assert result["verdict"] == "PASS"


def test_g1a_excludes_warmup_and_unadmitted_rows() -> None:
    rows = paired_parity_rows(W2)
    rows.append(raw_row(W2, 1, 1, 99.0, ["zz"], {"zz": 0.0}, phase="warmup"))  # warm-up never pairs
    rows.append(
        raw_row(W2, 1, 2, 99.0, ["zz"], {"zz": 0.0}, admitted=False, reason="excluded")
    )  # excluded row
    result = sm.g1a(rows)
    assert result["verdict"] == "PASS"
    assert result["numbers"]["pairs"] == 3


def test_g1b_uses_w4_control() -> None:
    assert sm.g1b(paired_parity_rows(W4))["verdict"] == "PASS"
    assert sm.g1b(paired_parity_rows(W4, swap=True))["verdict"] == "FAIL"


# ── G1c: per-response admission truth ─────────────────────────────────


def test_g1c_pass_on_clean_rows() -> None:
    rows = latency_rows(W3, W4, 40.0, 50.0)
    result = sm.g1c(rows)
    assert result["verdict"] == "PASS"


def test_g1c_fails_on_recorded_violation() -> None:
    rows = latency_rows(W3, W4, 40.0, 50.0)
    rows.append(
        raw_row(
            W3,
            1,
            9,
            5.0,
            ["a"],
            {"a": 0.5},
            admitted=False,
            rerank_ok=False,
            reason="unreranked response",
        )
    )
    result = sm.g1c(rows)
    assert result["verdict"] == "FAIL"


def test_g1c_fails_on_admitted_despite_false_flag() -> None:
    rows = latency_rows(W3, W4, 40.0, 50.0)
    rows.append(raw_row(W3, 1, 9, 5.0, ["a"], {"a": 0.5}, route_ok=False))
    result = sm.g1c(rows)
    assert result["verdict"] == "FAIL"


# ── G2/G3: latency ratios ─────────────────────────────────────────────


def test_g2_pass_at_ratio_boundary() -> None:
    result = sm.g2(latency_rows(W3, W4, 40.0, 50.0))
    assert result["verdict"] == "PASS"  # ratio 0.8 exactly: <= 0.8 passes


def test_g2_fail_above_boundary() -> None:
    result = sm.g2(latency_rows(W3, W4, 45.0, 50.0))
    assert result["verdict"] == "FAIL"


def test_g2_median_of_per_block_ratios() -> None:
    rows = latency_rows(W3, W4, 35.0, 50.0, blocks=(1,))  # 0.7
    rows += latency_rows(W3, W4, 45.0, 50.0, blocks=(2,))  # 0.9
    result = sm.g2(rows)  # median of [0.7, 0.9] == 0.8 -> PASS
    assert result["verdict"] == "PASS"


def test_g2_excludes_warmup_and_unadmitted() -> None:
    rows = latency_rows(W3, W4, 40.0, 50.0)
    rows.append(raw_row(W3, 1, 7, 9999.0, ["a"], {"a": 0.5}, phase="warmup"))
    rows.append(raw_row(W3, 2, 7, 9999.0, ["a"], {"a": 0.5}, admitted=False, reason="late"))
    assert sm.g2(rows)["verdict"] == "PASS"


def test_g3_uses_w1_control() -> None:
    assert sm.g3(latency_rows(W3, W1, 40.0, 50.0))["verdict"] == "PASS"
    assert sm.g3(latency_rows(W3, W1, 45.0, 50.0))["verdict"] == "FAIL"


# ── G4: cumulative break-even ─────────────────────────────────────────


def test_g4_pass_with_early_crossover() -> None:
    checkpoint, rows = g4_fixture(startup_s=0.05, warmup_s=0.05)
    # persistent(n) = 0.1s + 10ms*n versus W1 20ms*n -> N* = 10.
    result = sm.g4(checkpoint, rows)
    assert result["verdict"] == "PASS"  # bound far below 150 requests
    assert result["verdict"] in VERDICTS


def test_g4_fail_with_late_crossover() -> None:
    checkpoint, rows = g4_fixture(startup_s=5.0, warmup_s=0.05)
    result = sm.g4(checkpoint, rows)  # N* ~ 500 > 150
    assert result["verdict"] == "FAIL"


# ── G5: per-lifetime memory ceilings ──────────────────────────────────


def passing_lifetime(lifetime: int) -> list[dict]:
    rows = [mem_row(lifetime, 1, 500.0, 300.0, 800.0)]  # early sample
    rows += [
        mem_row(lifetime, req, 600.0, 300.0, 1000.0) for req in range(801, 1001, 10)
    ]  # plateau window
    return rows


def test_g5_pass_within_ceilings() -> None:
    result = sm.g5(passing_lifetime(1))
    assert result["verdict"] == "PASS"


def test_g5_one_failing_lifetime_fails_gate() -> None:
    rows = passing_lifetime(1)
    rows += [
        mem_row(2, req, 800.0, 300.0, 1100.0) for req in range(801, 1001, 10)
    ]  # worker 800 > 750 MiB
    assert sm.g5(rows)["verdict"] == "FAIL"


def test_g5_tree_peak_over_ceiling_fails() -> None:
    rows = passing_lifetime(1)
    rows.append(mem_row(1, 500, 700.0, 400.0, 1600.0))  # peak 1600 > 1500
    assert sm.g5(rows)["verdict"] == "FAIL"


def test_g5_missing_samples_not_evaluable() -> None:
    assert sm.g5([])["verdict"] == "NOT_EVALUABLE"


# ── G6: post-burn-in growth ───────────────────────────────────────────


def test_g6_pass_flat_growth() -> None:
    samples = growth_samples(1, W3, 0.0) + growth_samples(1, W4, 0.0, block=2)
    result = sm.g6(samples)
    assert result["verdict"] == "PASS"


def test_g6_fail_on_growth_at_or_above_bound() -> None:
    samples = (
        growth_samples(1, W3, 30.0)  # ~30 MiB per 1000 requests
        + growth_samples(1, W4, 0.0, block=2)
    )
    assert sm.g6(samples)["verdict"] == "FAIL"


def test_g6_missing_samples_not_evaluable() -> None:
    assert sm.g6([])["verdict"] == "NOT_EVALUABLE"


# ── G7/G8: lifecycle probes ───────────────────────────────────────────


def test_g7_all_required_probes_pass() -> None:
    rows = [probe_row(name, "pass") for name in G7_PROBES]
    assert sm.g7(rows)["verdict"] == "PASS"


def test_g7_fail_on_failing_probe() -> None:
    rows = [probe_row(name, "pass") for name in G7_PROBES]
    rows.append(probe_row("worker-death", "fail"))
    assert sm.g7(rows)["verdict"] == "FAIL"


def test_g7_fail_on_missing_probe() -> None:
    rows = [probe_row(name, "pass") for name in G7_PROBES if name != "request-deadline"]
    assert sm.g7(rows)["verdict"] == "FAIL"


def test_g8_all_required_probes_pass() -> None:
    rows = [probe_row(name, "pass") for name in G8_PROBES]
    assert sm.g8(rows)["verdict"] == "PASS"


def test_g8_fail_on_missing_probe() -> None:
    rows = [probe_row(name, "pass") for name in G8_PROBES if name != "parent-death-inflight"]
    assert sm.g8(rows)["verdict"] == "FAIL"


# ── load_rows ─────────────────────────────────────────────────────────


def test_load_rows_reads_all_four_artefacts(tmp_path) -> None:
    rows = [raw_row(W3, 1, 1, 10.0, ["a"], {"a": 0.5})]
    samples = [mem_row(1, 801, 600.0, 300.0, 1000.0)]
    probes = [probe_row("worker-death", "pass")]
    checkpoint = art.build_checkpoint(
        experiment_id="5b-persistent-mps-reranker-worker",
        plan_sha256="00" * 32,
        completed=[art.checkpoint_key(W3, 1)],
        records={art.checkpoint_key(W3, 1): {"status": "complete"}},
    )
    art.append_jsonl(tmp_path / "raw_rows.jsonl", rows)
    art.append_jsonl(tmp_path / "memory_samples.jsonl", samples)
    art.append_jsonl(tmp_path / "lifecycle_probes.jsonl", probes)
    art.write_json_atomic(tmp_path / "eval_results_checkpoint.json", checkpoint)

    loaded = sm.load_rows(tmp_path)
    assert set(loaded) >= {"raw_rows", "memory_samples", "probe_rows", "checkpoint"}
    assert loaded["raw_rows"] == rows
    assert loaded["memory_samples"] == samples
    assert loaded["probe_rows"] == probes
    assert loaded["checkpoint"]["completed"] == checkpoint["completed"]


# ── canonical correctness projection ──────────────────────────────────


def projection_rows() -> list[dict]:
    return [
        raw_row(W3, 1, 5, 10.0, ["a", "b"], {"a": 0.9, "b": 0.4}),
        raw_row(W3, 1, 6, 11.0, ["b", "a"], {"b": 0.7, "a": 0.2}),
        raw_row(W2, 1, 5, 12.0, ["a", "b"], {"a": 0.89, "b": 0.41}),
    ]


def test_projection_canonical_shape_and_sorted_keys() -> None:
    projection = sm.correctness_projection(projection_rows())
    assert set(projection) == {"pairs"}
    keys = list(projection["pairs"])
    assert keys == sorted(keys)
    assert keys == ["1:5:torch_mps_fresh", "1:5:torch_mps_persistent", "1:6:torch_mps_persistent"]
    for pair in projection["pairs"].values():
        assert set(pair) == {"ranking", "scores"}


def test_projection_identical_across_two_calls() -> None:
    rows = projection_rows()
    first = json.dumps(sm.correctness_projection(rows), sort_keys=True)
    second = json.dumps(sm.correctness_projection(rows), sort_keys=True)
    assert first == second


def test_projection_excludes_timing_and_process_fields() -> None:
    """Latency, PIDs and clocks differ; the projection must not."""
    base = projection_rows()
    varied = [
        raw_row(W3, 1, 5, 999.0, ["a", "b"], {"a": 0.9, "b": 0.4}, worker_pid=8888),
        raw_row(W3, 1, 6, 123.0, ["b", "a"], {"b": 0.7, "a": 0.2}, worker_pid=8888),
        raw_row(W2, 1, 5, 321.0, ["a", "b"], {"a": 0.89, "b": 0.41}, worker_pid=8888),
    ]
    assert json.dumps(sm.correctness_projection(base), sort_keys=True) == json.dumps(
        sm.correctness_projection(varied), sort_keys=True
    )
