"""Fast Experiment 5 harness tests (no model load, no network, no store).

Loads the harness modules via importlib because the experiment directory
name contains dashes (same pattern as the sibling experiment harness
tests).  Everything here is deterministic and finishes in seconds.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EXP_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str) -> object:
    """Load a module from the experiment directory by file path."""
    spec = importlib.util.spec_from_file_location(name, EXP_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


harness = _load("harness", "harness.py")
make_workload = _load("exp5_make_workload", "make_workload.py")
run_eval = _load("exp5_run_eval", "run_eval.py")


def _plan_payload() -> dict:
    return json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))


# ── D15: plan agreement ───────────────────────────────────────────────


def test_plan_runner_cell_agreement() -> None:
    from experiments._lib.plan import ExperimentPlan

    plan = ExperimentPlan.from_json(EXP_DIR / "plan.json")
    plan.assert_runner_cells(harness.build_cell_matrix())


def test_plan_agreement_rejects_mutated_matrix() -> None:
    from experiments._lib.plan import ExperimentPlan

    plan = ExperimentPlan.from_json(EXP_DIR / "plan.json")
    mutated = harness.build_cell_matrix()
    mutated[0] = {"id": "onnx_cpu", "factors": {"backend": "torch", "device": "cpu"}}
    with pytest.raises(AssertionError, match="onnx_cpu"):
        plan.assert_runner_cells(mutated)


def test_plan_declares_exactly_four_routes() -> None:
    cells = harness.build_cell_matrix()
    assert [cell["id"] for cell in cells] == [
        "onnx_cpu",
        "onnx_coreml",
        "torch_cpu",
        "torch_mps",
    ]


# ── Workload identity (protocol section 9) ────────────────────────────


def test_workload_identity_matches_plan() -> None:
    payload = _plan_payload()
    assert payload["controlled_variables"]["workload_identity"] == harness.workload_identity()


def test_workload_shape() -> None:
    workload = harness.load_workload()
    assert workload["num_queries"] == 24
    assert workload["candidates_per_query"] == 50
    counts = workload["margin_class_counts"]
    assert counts == {"medium": 8, "near_tie": 8, "wide": 8}
    for query in workload["queries"]:
        texts = [candidate["text"] for candidate in query["candidates"]]
        assert len(texts) == 50
        assert len(set(texts)) == 50, "candidate texts must be unique per query"
        assert all(text.strip() for text in texts)


def test_workload_regenerates_byte_identically() -> None:
    payload = make_workload.serialise(make_workload.build_workload())
    committed = (EXP_DIR / "workload.json").read_text(encoding="utf-8")
    assert payload == committed


# ── Counterbalancing (protocol section 10) ────────────────────────────


def test_counterbalanced_rotation_covers_start_positions() -> None:
    cells = harness.build_cell_matrix()
    starts: list[str] = []
    for repetition in range(3):
        order = harness.counterbalanced_order(cells, repetition)
        assert sorted(cell["id"] for cell in order) == sorted(cell["id"] for cell in cells)
        starts.append(order[0]["id"])
    assert len(set(starts)) == 3, "each repetition should start on a different cell"


# ── Route policy (protocol sections 4-5, 12) ──────────────────────────


def test_route_env_overrides() -> None:
    cells = {cell["id"]: cell for cell in harness.build_cell_matrix()}
    coreml = harness.route_env_overrides(cells["onnx_coreml"])
    assert coreml["RERANK_ONNX_PROVIDER"] == "coreml"
    assert coreml["HF_HUB_OFFLINE"] == "1"
    cpu = harness.route_env_overrides(cells["onnx_cpu"])
    assert cpu["RERANK_ONNX_PROVIDER"] == "cpu"
    torch_cpu = harness.route_env_overrides(cells["torch_cpu"])
    assert "RERANK_ONNX_PROVIDER" not in torch_cpu
    assert torch_cpu["HF_HUB_OFFLINE"] == "1"


def test_device_policy_cpu_hides_mps() -> None:
    torch = pytest.importorskip("torch")
    cells = {cell["id"]: cell for cell in harness.build_cell_matrix()}
    original = torch.backends.mps.is_available
    try:
        harness.apply_device_policy(cells["torch_cpu"])
        assert torch.backends.mps.is_available() is False
        # The torch_mps policy is a deliberate no-op: it must leave the
        # current callable untouched (device resolution stays with the
        # library default, which preflight then verifies is MPS).
        current = torch.backends.mps.is_available
        harness.apply_device_policy(cells["torch_mps"])
        assert torch.backends.mps.is_available is current
    finally:
        torch.backends.mps.is_available = original


class _FakeSession:
    def __init__(self, providers: list[str]) -> None:
        self._providers = providers

    def get_providers(self) -> list[str]:
        return list(self._providers)


class _FakeOnnxReranker:
    backend_name = "onnx"
    _model_id = harness.MODEL_ID
    last_loaded_variant = "onnx/model_qint8_arm64.onnx"

    def __init__(self, providers: list[str]) -> None:
        self._session = _FakeSession(providers)


class _FakeTorchReranker:
    backend_name = "torch"
    _model_id = harness.MODEL_ID
    last_loaded_device = "cpu"

    def __init__(self, device: str) -> None:
        self.last_loaded_device = device


def test_assert_effective_route_onnx_first_provider() -> None:
    cells = {cell["id"]: cell for cell in harness.build_cell_matrix()}
    ok = harness.assert_effective_route(
        cells["onnx_coreml"],
        _FakeOnnxReranker(["CoreMLExecutionProvider", "CPUExecutionProvider"]),
    )
    assert ok["onnx_effective_providers"][0] == "CoreMLExecutionProvider"
    with pytest.raises(AssertionError, match="silent fallback"):
        harness.assert_effective_route(
            cells["onnx_coreml"],
            _FakeOnnxReranker(["CPUExecutionProvider"]),
        )
    with pytest.raises(AssertionError, match="no loaded ONNX session"):
        harness.assert_effective_route(
            cells["onnx_cpu"],
            _FakeOnnxReranker([]),
        )


def test_assert_effective_route_torch_prefix() -> None:
    cells = {cell["id"]: cell for cell in harness.build_cell_matrix()}
    ok = harness.assert_effective_route(cells["torch_mps"], _FakeTorchReranker("mps"))
    assert ok["torch_effective_device"] == "mps"
    with pytest.raises(AssertionError, match="effective device"):
        harness.assert_effective_route(cells["torch_mps"], _FakeTorchReranker("cpu"))


# ── Fallback detection and measured-pass rows (D16) ───────────────────


class _FakeScoringReranker:
    backend_name = "fake"
    last_failure_reason = None

    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        for index, result in enumerate(results):
            result["score"] = 1.0 - index * 0.01
            result["_reranked"] = True
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]


class _FailingReranker(_FakeScoringReranker):
    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        for result in results:
            result["_reranked"] = False
        self.last_failure_reason = "inference failed: simulated"
        return results[:top_k]


def test_detect_inference_fallback() -> None:
    clean = _FakeScoringReranker()
    ranked = clean.rerank("q", [{"text": "a", "score": 0.0}], top_k=1)
    assert harness.detect_inference_fallback(clean, ranked) is None
    failing = _FailingReranker()
    degraded = failing.rerank("q", [{"text": "a", "score": 0.0}], top_k=1)
    reason = harness.detect_inference_fallback(failing, degraded)
    assert reason is not None and "simulated" in reason


def test_run_workload_pass_rows_validate_against_d16() -> None:
    from experiments._lib import stats as stats_lib

    workload = harness.load_workload()
    rows, _total = harness.run_workload_pass(
        reranker=_FakeScoringReranker(),
        workload=workload,
        cell_id="torch_cpu",
        repetition=0,
        pass_index=0,
        phase="measured",
    )
    assert len(rows) == workload["num_queries"]
    stats_lib.validate_per_query_rows(rows)
    first = rows[0]
    assert len(first["metrics"]["scores"]) == 50
    assert len(first["metrics"]["ranking"]) == 50
    assert first["pass_index"] == 0 and first["phase"] == "measured"


def test_run_workload_pass_raises_on_fallback() -> None:
    workload = harness.load_workload()
    with pytest.raises(RuntimeError, match="fallback"):
        harness.run_workload_pass(
            reranker=_FailingReranker(),
            workload=workload,
            cell_id="onnx_coreml",
            repetition=0,
            pass_index=0,
            phase="warmup",
        )


# ── Child plumbing and rollup (TDR-014 rules 7-8) ─────────────────────


def test_child_argv_and_result_path() -> None:
    argv = harness.child_argv(
        cell_id="torch_mps",
        repetition=2,
        output_dir=Path("/tmp/exp5-out"),
        measured_passes=5,
        warmup_passes=1,
        dry_run=False,
    )
    assert argv[0].endswith("child_run.py")
    assert "--cell" in argv and "torch_mps" in argv
    assert "--dry-run" not in argv
    path = harness.child_result_path(Path("/tmp/exp5-out"), "torch_mps", 2)
    assert path.name == "torch_mps__rep2.json"


def test_rollup_cells_statuses() -> None:
    records = [
        {"cell_id": "onnx_cpu", "repetition": 0, "status": "complete"},
        {"cell_id": "onnx_cpu", "repetition": 1, "status": "complete"},
        {"cell_id": "onnx_cpu", "repetition": 2, "status": "complete"},
        {"cell_id": "onnx_coreml", "repetition": 0, "status": "complete"},
        {
            "cell_id": "onnx_coreml",
            "repetition": 1,
            "status": "invalid",
            "reason": "preflight failed: provider mismatch",
        },
        {"cell_id": "torch_cpu", "repetition": 0, "status": "complete"},
    ]
    rolled = run_eval.rollup_cells(records, expected_repetitions=3)
    by_id = {record["cell_id"]: record for record in rolled}
    assert by_id["onnx_cpu"]["status"] == "complete"
    assert by_id["onnx_coreml"]["status"] == "invalid"
    assert "provider mismatch" in by_id["onnx_coreml"]["reason"]
    assert by_id["torch_cpu"]["status"] == "incomplete"


def test_evaluate_child_result_validates_rows() -> None:
    bad_rows_child = {
        "cell_id": "torch_cpu",
        "repetition": 0,
        "status": "complete",
        "rows": [{"cell_id": "torch_cpu", "query_id": "q000"}],
    }
    record = run_eval.evaluate_child_result(bad_rows_child)
    assert record["status"] == "invalid"
    assert "D16 validation" in record["reason"]
