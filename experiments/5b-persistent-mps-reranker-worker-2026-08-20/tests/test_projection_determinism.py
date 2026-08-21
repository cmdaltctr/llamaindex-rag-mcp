"""Canonical correctness-projection determinism (OpenSpec task 4.3) — RED
until implemented.

Builds one frozen raw fixture twice — with deliberately different latency,
worker PID and clock evidence — writes it to two independent output
directories as JSON-lines artefacts, and asserts the canonical projection
regenerated from each is byte-identical under ``json.dumps(sort_keys=True)``.
Also exercises the tolerance-based inference-comparison semantics that
fresh-run comparisons must use instead of byte equality of scores.
"""

from __future__ import annotations

import json

import artefacts as art
from _lazy_module import LazyModule

se = LazyModule("stats_extras")  # RED until implemented
sm = LazyModule("summarise_eval")  # RED until implemented

W3 = "torch_mps_persistent"
W2 = "torch_mps_fresh"
TOLERANCE = 1e-4  # G1 registered tolerance (protocol section 10)


def _fixture_rows(*, latency: float, worker_pid: int) -> list[dict]:
    """The frozen fixture: fixed pairs, variable timing/process evidence."""
    rows = []
    for block, req, ranking, scores in (
        (1, 1, ["a", "b", "c"], {"a": 0.91, "b": 0.55, "c": 0.10}),
        (1, 2, ["b", "a", "c"], {"b": 0.80, "a": 0.42, "c": 0.05}),
        (1, 3, ["c", "b", "a"], {"c": 0.77, "b": 0.30, "a": 0.02}),
        (2, 1, ["a", "c", "b"], {"a": 0.66, "c": 0.60, "b": 0.11}),
        (2, 2, ["b", "c", "a"], {"b": 0.95, "c": 0.25, "a": 0.01}),
    ):
        for cell in (W3, W2):
            metrics = {
                "scores": dict(scores),
                "ranking": list(ranking),
                "route_ok": True,
                "rerank_ok": True,
                "cardinality_ok": True,
                "generation_ok": True,
                "admitted": True,
            }
            rows.append(
                art.build_raw_row(
                    cell_id=cell,
                    block=block,
                    lifetime=1,
                    request_index=req,
                    query_id=f"pass{block - 1}_q{req - 1:02d}",
                    phase="measured",
                    source="primary",
                    latency_ms=latency + (0.5 if cell == W2 else 0.0),
                    generation=0,
                    worker_pid=worker_pid,
                    metrics=metrics,
                )
            )
    return rows


def _write_output_dir(tmp_path, rows) -> None:
    art.append_jsonl(tmp_path / "raw_rows.jsonl", rows)
    art.append_jsonl(tmp_path / "memory_samples.jsonl", [])
    art.append_jsonl(tmp_path / "lifecycle_probes.jsonl", [])
    art.write_json_atomic(
        tmp_path / "eval_results_checkpoint.json",
        art.build_checkpoint(
            experiment_id="5b-persistent-mps-reranker-worker",
            plan_sha256="00" * 32,
            completed=[],
            records={},
        ),
    )


def _project(dir_path) -> str:
    loaded = sm.load_rows(dir_path)
    return json.dumps(sm.correctness_projection(loaded["raw_rows"]), sort_keys=True)


def test_projection_byte_identical_across_two_generations(tmp_path) -> None:
    """Two independent fixture generations project to identical bytes."""
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    _write_output_dir(run_a, _fixture_rows(latency=12.5, worker_pid=1111))
    _write_output_dir(run_b, _fixture_rows(latency=999.0, worker_pid=2222))

    bytes_a = _project(run_a)
    bytes_b = _project(run_b)
    assert bytes_a == bytes_b
    assert bytes_a  # non-empty projection

    projection = json.loads(bytes_a)
    # Ten canonical pairs: five requests x two cells.
    assert len(projection["pairs"]) == 10
    for key, pair in projection["pairs"].items():
        block, req, cell = key.split(":")
        assert block.isdigit() and req.isdigit() and cell in (W3, W2)
        assert set(pair) == {"ranking", "scores"}


def test_projection_repeated_from_same_dir_is_stable(tmp_path) -> None:
    """Regenerating from one frozen fixture never drifts."""
    out = tmp_path / "out"
    _write_output_dir(out, _fixture_rows(latency=7.0, worker_pid=3))
    assert _project(out) == _project(out)


def test_fresh_inference_comparison_uses_tolerance_not_bytes(tmp_path) -> None:
    """Two fresh runs with sub-tolerance score drift compare equal.

    Byte equality would reject the drifted scores; the registered semantics
    accept any paired delta within ``1e-4`` when rankings are identical.
    """
    baseline_rows = _fixture_rows(latency=10.0, worker_pid=1)
    drifted_rows = []
    for row in _fixture_rows(latency=13.0, worker_pid=2):
        drifted = dict(row)
        drifted["metrics"] = {
            **row["metrics"],
            "scores": {doc: score + 5e-5 for doc, score in row["metrics"]["scores"].items()},
        }
        drifted_rows.append(drifted)

    projection_a = sm.correctness_projection(baseline_rows)
    projection_b = sm.correctness_projection(drifted_rows)
    assert json.dumps(projection_a, sort_keys=True) != json.dumps(
        projection_b, sort_keys=True
    )  # bytes legitimately differ

    equivalent = all(
        se.rankings_equal(pair_a["ranking"], pair_b["ranking"])
        and se.paired_max_abs_delta(pair_a["scores"], pair_b["scores"]) <= TOLERANCE
        for pair_a, pair_b in zip(
            projection_a["pairs"].values(), projection_b["pairs"].values(), strict=False
        )
    )
    assert equivalent

    # A ranking flip is never absorbable by the tolerance.
    flipped = _fixture_rows(latency=10.0, worker_pid=1)
    flipped[0]["metrics"] = {
        **flipped[0]["metrics"],
        "ranking": list(reversed(flipped[0]["metrics"]["ranking"])),
    }
    projection_c = sm.correctness_projection(flipped)
    first_a = next(iter(projection_a["pairs"].values()))
    first_c = next(iter(projection_c["pairs"].values()))
    assert not se.rankings_equal(first_a["ranking"], first_c["ranking"])
