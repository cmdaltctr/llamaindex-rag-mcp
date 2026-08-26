"""Fast tests for the harness module (OpenSpec task 4.1) — RED until implemented.

Plan/runner cell agreement against the committed plan.json, the frozen
counterbalancing table from protocol.md section 15, frozen workload and
longevity identities (including a tampered-copy rejection), ordered primary
request cycling over the 24-query Experiment 5 workload, parent Torch-stack
purity, and the plan SHA-256.  No model, no network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from _lazy_module import LazyModule

harness = LazyModule("harness")  # RED (ModuleNotFoundError) until implemented

EXP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EXP_DIR.parents[1]
WORKLOAD_FILE = (
    REPO_ROOT
    / "experiments"
    / "example"
    / "experiment-5-reranker-backend-device-parity"
    / "workload.json"
)

EXPECTED_COUNTERBALANCE = {
    1: (
        "torch_cpu_fresh",
        "torch_mps_persistent",
        "torch_mps_fresh",
        "torch_cpu_persistent",
        "onnx_cpu_in_process",
    ),
    2: (
        "torch_mps_fresh",
        "torch_cpu_persistent",
        "onnx_cpu_in_process",
        "torch_cpu_fresh",
        "torch_mps_persistent",
    ),
    3: (
        "onnx_cpu_in_process",
        "torch_cpu_fresh",
        "torch_mps_persistent",
        "torch_mps_fresh",
        "torch_cpu_persistent",
    ),
}

ALL_CELL_IDS = set(EXPECTED_COUNTERBALANCE[1])
TORCH_CELL_IDS = ALL_CELL_IDS - {"onnx_cpu_in_process"}


# ── module constants and identities ───────────────────────────────────


def test_module_constants() -> None:
    assert harness.EXPERIMENT_ID == "5b-persistent-mps-reranker-worker"
    assert harness.PROTOCOL_VERSION == "1.1"
    assert harness.WORKLOAD_IDENTITY == (
        "sha256:bb412ddcd1e3c855a6bd78e06e61ff6a5bf72592a1566602c3b769524d06e1dc"
    )
    assert harness.LONGEVITY_IDENTITY == (
        "sha256:5463c0a9991a9348a3e1ca9a3dca9a4db9f9419067a3f5a0bf83f0c1eb9978e7"
    )
    assert isinstance(harness.PLAN_PATH, Path) and harness.PLAN_PATH.exists()
    assert isinstance(harness.WORKLOAD_PATH, Path) and harness.WORKLOAD_PATH.exists()
    assert isinstance(harness.LONGEVITY_PATH, Path) and harness.LONGEVITY_PATH.exists()


def test_plan_sha256_matches_committed_file() -> None:
    digest = hashlib.sha256(harness.PLAN_PATH.read_bytes()).hexdigest()
    assert harness.plan_sha256() == digest


# ── plan / runner agreement ───────────────────────────────────────────


def test_build_cell_matrix_matches_plan() -> None:
    from experiments._lib.plan import ExperimentPlan

    plan = ExperimentPlan.from_json(harness.PLAN_PATH)
    cells = harness.build_cell_matrix()
    assert len(cells) == 5
    plan.assert_runner_cells(cells)  # raises AssertionError on any drift

    by_id = {cell["id"]: cell for cell in cells}
    assert set(by_id) == ALL_CELL_IDS
    for cell_id in TORCH_CELL_IDS:
        assert set(by_id[cell_id]["factors"]) == {
            "backend",
            "device",
            "process_shape",
            "precision",
        }
    assert set(by_id["onnx_cpu_in_process"]["factors"]) == {
        "backend",
        "device",
        "process_shape",
        "precision",
        "onnx_provider",
    }


def test_assert_plan_agreement_accepts_committed_plan() -> None:
    plan = harness.load_plan()
    harness.assert_plan_agreement(plan)  # must not raise


# ── counterbalancing table (protocol section 15) ──────────────────────


def test_counterbalance_table_matches_protocol() -> None:
    assert harness.COUNTERBALANCE_TABLE == EXPECTED_COUNTERBALANCE


def test_counterbalance_each_cell_once_and_rotated_positions() -> None:
    table = harness.COUNTERBALANCE_TABLE
    assert set(table) == {1, 2, 3}
    for _block, order in table.items():
        assert len(order) == 5
        assert set(order) == ALL_CELL_IDS  # each cell exactly once per block

    # Each cell occupies a different position in every block.
    for cell in ALL_CELL_IDS:
        positions = [order.index(cell) for order in table.values()]
        assert len(positions) == len(set(positions)), (
            f"cell {cell!r} repeats a position across blocks: {positions}"
        )


# ── frozen identities ─────────────────────────────────────────────────


def test_assert_frozen_identities_passes_on_committed_files() -> None:
    harness.assert_frozen_identities()  # must not raise


def test_assert_frozen_identities_rejects_tampered_workload(tmp_path, monkeypatch) -> None:
    tampered = tmp_path / "workload.json"
    payload = json.loads(harness.WORKLOAD_PATH.read_text(encoding="utf-8"))
    payload["queries"][0]["text"] = "tampered query text"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(harness, "WORKLOAD_PATH", tampered)
    with pytest.raises((AssertionError, ValueError)):
        harness.assert_frozen_identities()


def test_assert_frozen_identities_rejects_tampered_longevity(tmp_path, monkeypatch) -> None:
    tampered = tmp_path / "longevity_schedule.json"
    payload = json.loads(harness.LONGEVITY_PATH.read_text(encoding="utf-8"))
    payload["requests"][0]["stratum_candidate_count"] = 999
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(harness, "LONGEVITY_PATH", tampered)
    with pytest.raises((AssertionError, ValueError)):
        harness.assert_frozen_identities()


# ── ordered primary workload cycling ──────────────────────────────────


def test_ordered_primary_request_cycles_and_formats_ids() -> None:
    workload = json.loads(WORKLOAD_FILE.read_text(encoding="utf-8"))
    queries = workload["queries"]
    assert len(queries) == 24

    for n, expected_pass, expected_query in (
        (0, 0, 0),
        (23, 0, 23),
        (24, 1, 0),
        (25, 1, 1),
        (47, 1, 23),
    ):
        request = harness.ordered_primary_request(n)
        assert request["pass_index"] == expected_pass
        assert request["query_id"] == f"pass{expected_pass}_q{expected_query:02d}"
        assert request["query"] == queries[expected_query]["text"]
        assert request["candidates"] == queries[expected_query]["candidates"]


def test_load_workload_returns_experiment_five_workload() -> None:
    workload = harness.load_workload()
    expected = json.loads(WORKLOAD_FILE.read_text(encoding="utf-8"))
    assert workload == expected


# ── parent purity ─────────────────────────────────────────────────────


def test_assert_parent_torch_free_is_empty_now() -> None:
    """The test parent imports no Torch-stack module, so the proof is empty."""
    assert harness.assert_parent_torch_free() == []
