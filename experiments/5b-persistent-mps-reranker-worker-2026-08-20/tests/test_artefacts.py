"""Fast tests for artefacts.py row builders (OpenSpec task 4.1).

Covers the happy paths and every documented invalid-input class for the
raw-row, memory-sample and probe-row builders, the JSON-lines and atomic
JSON writers, the checkpoint builders, and the parent Torch-stack purity
probe (via monkeypatched ``sys.modules`` — no real Torch import).
"""

from __future__ import annotations

import json
import sys
import types

import artefacts as art
import protocol_frames as pf


def _raw_metrics() -> dict:
    return {
        "scores": {"a": 0.9, "b": 0.1},
        "ranking": ["a", "b"],
        "route_ok": True,
        "rerank_ok": True,
        "cardinality_ok": True,
        "generation_ok": True,
        "admitted": True,
    }


# ── build_raw_row ─────────────────────────────────────────────────────


def test_build_raw_row_happy_path() -> None:
    row = art.build_raw_row(
        cell_id="torch_mps_persistent",
        block=1,
        lifetime=1,
        request_index=7,
        query_id="pass0_q07",
        phase="measured",
        source="primary",
        latency_ms=42.5,
        generation=0,
        worker_pid=111,
        metrics=_raw_metrics(),
    )
    for field in art.RAW_ROW_REQUIRED:
        assert field in row
    assert row["latency_ms"] == 42.5
    assert row["phase"] == "measured"
    assert row["source"] == "primary"
    assert row["parent_pid"] > 0  # defaults to the calling process
    assert row["warmup_pass"] is False
    assert "stratum" not in row

    warm = art.build_raw_row(
        cell_id="torch_cpu_persistent",
        block=1,
        lifetime=1,
        request_index=0,
        query_id="pass0_q00",
        phase="warmup",
        source="longevity",
        latency_ms=1.0,
        generation=0,
        worker_pid=111,
        metrics=_raw_metrics(),
        warmup_pass=True,
        stratum={"candidates": 50, "tokens": 128},
    )
    assert warm["warmup_pass"] is True
    assert warm["stratum"] == {"candidates": 50, "tokens": 128}


def test_build_raw_row_rejects_bad_phase_and_source() -> None:
    for bad_phase in ("Measured", "burn-in", ""):
        try:
            art.build_raw_row(
                cell_id="c",
                block=1,
                lifetime=1,
                request_index=0,
                query_id="q",
                phase=bad_phase,
                source="primary",
                latency_ms=1.0,
                generation=0,
                worker_pid=1,
                metrics={},
            )
            raise AssertionError(f"phase={bad_phase!r} must be rejected")
        except ValueError:
            pass
    try:
        art.build_raw_row(
            cell_id="c",
            block=1,
            lifetime=1,
            request_index=0,
            query_id="q",
            phase="measured",
            source="secondary",
            latency_ms=1.0,
            generation=0,
            worker_pid=1,
            metrics={},
        )
        raise AssertionError("source must be validated")
    except ValueError:
        pass


# ── build_memory_sample ───────────────────────────────────────────────


def test_build_memory_sample_fields() -> None:
    sample = art.build_memory_sample(
        cell_id="torch_mps_persistent",
        block=1,
        lifetime=2,
        request_index=250,
        worker_rss_bytes=524_288_000,
        parent_rss_bytes=314_572_800,
        tree_rss_bytes=838_860_800,
    )
    for field in art.MEMORY_SAMPLE_REQUIRED:
        assert field in sample
    assert sample["worker_rss_bytes"] == 524_288_000
    assert sample["tree_rss_bytes"] == 838_860_800
    assert sample["mps_current_allocated_bytes"] is None
    assert sample["mps_driver_allocated_bytes"] is None

    with_mps = art.build_memory_sample(
        cell_id="torch_mps_persistent",
        block=1,
        lifetime=2,
        request_index=251,
        worker_rss_bytes=1,
        parent_rss_bytes=2,
        tree_rss_bytes=3,
        mps_current_allocated_bytes=90_000,
        mps_driver_allocated_bytes=95_000,
    )
    assert with_mps["mps_current_allocated_bytes"] == 90_000
    assert with_mps["mps_driver_allocated_bytes"] == 95_000


# ── build_probe_row ───────────────────────────────────────────────────


def test_build_probe_row_happy_and_truncation() -> None:
    row = art.build_probe_row(
        probe="worker-death",
        worker_pid=222,
        outcome="pass",
        deadline_result="within_deadline",
        detail="SIGKILL observed",
        generation=0,
    )
    for field in art.PROBE_ROW_REQUIRED:
        assert field in row
    assert row["probe"] == "worker-death"
    assert row["outcome"] == "pass"

    long_detail = art.build_probe_row(
        probe="p",
        worker_pid=None,
        outcome="pass",
        deadline_result="ok",
        detail="x" * 5000,
    )
    assert len(long_detail["detail"]) == 2000


def test_build_probe_row_requires_required_kwargs() -> None:
    """Omitting a required keyword is a TypeError, not a silent row."""
    base = {
        "probe": "p",
        "worker_pid": 1,
        "outcome": "pass",
        "deadline_result": "ok",
        "detail": "d",
    }
    art.build_probe_row(**base)  # complete call works
    for missing in ("probe", "worker_pid", "outcome", "deadline_result", "detail"):
        call = dict(base)
        call.pop(missing)
        try:
            art.build_probe_row(**call)
            raise AssertionError(f"missing {missing!r} must be rejected")
        except TypeError:
            pass


# ── JSON-lines and atomic JSON writers ────────────────────────────────


def test_append_jsonl_and_read_jsonl_round_trip(tmp_path) -> None:
    path = tmp_path / "nested" / "rows.jsonl"
    row_a = {"id": 1, "text": "alpha"}
    row_b = {"id": 2, "text": "beta"}
    art.append_jsonl(path, row_a)  # single row
    art.append_jsonl(path, [row_b, row_a])  # batch, including a repeat
    rows = pf.read_jsonl(path)
    assert rows == [row_a, row_b, row_a]

    art.append_jsonl(path, [])  # empty batch is a no-op
    assert len(pf.read_jsonl(path)) == 3


def test_write_json_atomic_leaves_no_tmp_and_overwrites(tmp_path) -> None:
    path = tmp_path / "payload.json"
    art.write_json_atomic(path, {"v": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 1}
    assert not (tmp_path / "payload.json.tmp").exists()

    art.write_json_atomic(path, {"v": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 2}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["payload.json"]


# ── checkpoints ───────────────────────────────────────────────────────


def test_checkpoint_key_format() -> None:
    assert art.checkpoint_key("torch_mps_persistent", 3) == "torch_mps_persistent__block3"


def test_build_checkpoint_status_validation() -> None:
    good = art.build_checkpoint(
        experiment_id="5b-persistent-mps-reranker-worker",
        plan_sha256="ab" * 32,
        completed=["torch_mps_persistent__block2", "torch_mps_persistent__block1"],
        records={
            "torch_mps_persistent__block1": {"status": "complete"},
            "torch_mps_persistent__block2": {"status": "complete"},
            "torch_cpu_persistent__block1": {"status": "incomplete"},
        },
    )
    assert good["completed"] == sorted(good["completed"])
    assert good["experiment_id"] == "5b-persistent-mps-reranker-worker"
    for status in ("complete", "incomplete", "invalid"):
        art.build_checkpoint(
            experiment_id="e",
            plan_sha256="0" * 64,
            completed=[],
            records={"k": {"status": status}},
        )
    try:
        art.build_checkpoint(
            experiment_id="e",
            plan_sha256="0" * 64,
            completed=[],
            records={"k": {"status": "finished"}},
        )
        raise AssertionError("invalid status must be rejected")
    except ValueError:
        pass


# ── parent Torch-stack purity probe ───────────────────────────────────


def test_imported_torch_stack_modules_detection(monkeypatch) -> None:
    """Injected sys.modules entries are detected; a clean parent is empty."""
    fake_torch = types.ModuleType("torch")
    fake_st = types.ModuleType("sentence_transformers")
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)
    assert art.imported_torch_stack_modules() == [
        "sentence_transformers",
        "torch",
    ]

    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.delitem(sys.modules, "sentence_transformers", raising=False)
    monkeypatch.delitem(sys.modules, "transformers", raising=False)
    assert art.imported_torch_stack_modules() == []
