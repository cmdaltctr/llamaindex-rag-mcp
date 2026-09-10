"""Fail-before contracts for repair tasks 4.1-4.6 and 5.1, Experiment 26."""

from __future__ import annotations

import json
import os
import runpy
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
EXP = REPO / "experiments/26-query-instruction-ablation-2026-09-08"
GT = REPO / "experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/ground-truth.json"


def _validity():
    """Load the contractual shared helper lazily until it is implemented."""
    sys.path.insert(0, str(REPO / "experiments"))
    try:
        from _lib import checkpoint_validity
    except ImportError as exc:
        pytest.fail(f"implementation missing: experiments/_lib/checkpoint_validity.py ({exc})")
    return checkpoint_validity


def _row(query_id: str, category: str = "identifier-heavy", **changes: object) -> dict:
    """Well-formed row; the default matches expected["q0"] (see _expected)."""
    row = {"query_id": query_id, "category": category, "parent_ids": ["miss"], "latency_s": 0.1}
    row.update(changes)
    return row


def _expected(size: int = 6) -> dict[str, str]:
    return {f"q{index}": "semantic" if index % 2 else "identifier-heavy" for index in range(size)}


def _state(rows: list[dict], done: list[str] | None = None) -> dict:
    return {"rows": rows, "done": done if done is not None else [row["query_id"] for row in rows]}


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8")
    return path


class _Module(SimpleNamespace):
    """Expose runpy globals while preserving mutable module constants."""

    def __init__(self, values: dict) -> None:
        super().__init__(**values)
        object.__setattr__(self, "_values", values)

    def __setattr__(self, name: str, value: object) -> None:
        self._values[name] = value
        super().__setattr__(name, value)


def _load(path: Path, monkeypatch: pytest.MonkeyPatch) -> _Module:
    """Load an experiment module without reading .env or process settings."""
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(os, "environ", os.environ.copy())
    values = runpy.run_path(str(path))
    return _Module(values["main"].__globals__)


def _synthetic_inputs(root: Path, size: int = 6) -> tuple[Path, Path, Path, dict[str, str]]:
    expected = _expected(size)
    queries = [
        {
            "query_id": query_id,
            "query": query_id,
            "category": category,
            "relevant_parent_ids": [f"hit-{query_id}"],
            "nuggets": [],
        }
        for query_id, category in expected.items()
    ]
    plan = json.loads((EXP / "plan.json").read_text(encoding="utf-8"))
    manifest = {"embedding": {"candidate_instruction": "synthetic"}}
    return (
        _write(root / "ground-truth.json", {"queries": queries}),
        _write(root / "plan.json", plan),
        _write(root / "runtime_manifest.json", manifest),
        expected,
    )


def _summary(ns: SimpleNamespace, cells: Path, out_dir: Path) -> dict:
    return ns.summarise_from(cells, out_dir)


def _configure_exp26(
    ns: SimpleNamespace, root: Path, cells: Path, gt: Path, plan: Path, manifest: Path
) -> None:
    ns.EXP_DIR = root / "experiment"
    ns.EXP_DIR.mkdir(exist_ok=True)
    ns.GT_PATH, ns.PLAN_PATH, ns.MANIFEST_PATH = gt, plan, manifest
    ns.BASELINE_CKPT = cells / "raw_none.json"
    ns._write_results_md = lambda summary, plan: (root / "rendered.md").write_text(
        summary["headline"], encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Task 4.1: frozen historical prefix must not receive a promotion verdict.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not GT.exists(), reason="untracked ground truth is absent")
def test_four_query_prefix_is_incomplete_and_never_promoted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The audited four-row historical prefix must be INCOMPLETE, never PASS."""
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    cells = tmp_path / "cells"
    for cell in ("raw_none", "candidate_instruction"):
        source = EXP / "output/cells" / f"{cell}.json"
        state = json.loads(source.read_text(encoding="utf-8"))
        state["rows"] = state["rows"][:4]
        state["done"] = state["done"][:4]
        _write(cells / f"{cell}.json", state)
    plan = tmp_path / "plan.json"
    shutil.copy(EXP / "plan.json", plan)
    manifest = _write(tmp_path / "manifest.json", {"embedding": {"candidate_instruction": "x"}})
    _configure_exp26(ns, tmp_path, cells, GT, plan, manifest)
    summary = _summary(ns, cells, tmp_path / "out")
    assert summary.get("status") == "incomplete", (
        f"expected INCOMPLETE for the four-query prefix; current verdict={summary.get('verdict')}"
    )
    assert summary.get("verdict") != "PASS"
    assert "promotion" not in (tmp_path / "rendered.md").read_text(encoding="utf-8").lower()


# ---------------------------------------------------------------------------
# Task 4.2/4.3: shared cell membership and provenance contracts.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rows", "done", "status", "reason"),
    [
        ([_row("q0")], ["q0"], "incomplete", None),
        ([_row("q0"), _row("q0")], ["q0", "q0"], "invalid", "duplicate"),
        ([_row("outside")], ["outside"], "invalid", "unexpected"),
        ([_row("q0", "wrong")], ["q0"], "invalid", "category"),
        ([{"category": "semantic", "parent_ids": [], "latency_s": 0.1}], [], "invalid", "query_id"),
        (
            [{"query_id": "q0", "category": "semantic", "parent_ids": [1], "latency_s": 0.1}],
            ["q0"],
            "invalid",
            "parent_ids",
        ),
        ([_row("q0", latency_s=float("nan"))], ["q0"], "invalid", "latency"),
        ([_row("q0", latency_s=-0.1)], ["q0"], "invalid", "negative"),
        ([_row("q0")], ["q0", "q1"], "invalid", "done"),
    ],
)
def test_classify_cell_rejects_invalid_rows_and_marks_prefix_incomplete(
    rows, done, status, reason
) -> None:
    result = _validity().classify_cell(rows, done, _expected())
    assert result["status"] == status
    if reason:
        assert any(reason in item.lower() for item in result["reasons"])


def test_classify_cell_mutation_sanity_distinguishes_prefix_from_complete() -> None:
    expected = _expected()
    prefix = [_row(query_id, category) for query_id, category in list(expected.items())[:4]]
    complete = [_row(query_id, category) for query_id, category in expected.items()]
    prefix_status = _validity().classify_cell(
        prefix, [row["query_id"] for row in prefix], expected
    )["status"]
    assert prefix_status == "incomplete"
    complete_status = _validity().classify_cell(
        complete, [row["query_id"] for row in complete], expected
    )["status"]
    assert complete_status == "complete"


def test_equal_counts_with_different_ids_are_not_paired() -> None:
    reasons = _validity().pairing_ids_mismatch({"raw": {"q0", "q1"}, "candidate": {"q2", "q3"}})
    assert reasons and any("raw" in item and "candidate" in item for item in reasons)


def test_identity_and_resume_contracts(tmp_path: Path) -> None:
    helper = _validity()
    for name in ("plan", "ground-truth", "manifest", "code.py"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    identity = helper.run_identity(
        tmp_path / "plan",
        tmp_path / "ground-truth",
        tmp_path / "manifest",
        {"a": 1},
        [tmp_path / "code.py"],
    )
    same_again = helper.run_identity(
        tmp_path / "plan",
        tmp_path / "ground-truth",
        tmp_path / "manifest",
        {"a": 1},
        [tmp_path / "code.py"],
    )
    assert identity == same_again
    changed = {**identity, "plan": "changed"}
    assert helper.identity_mismatches(identity, changed) == ["plan"]
    resumed = helper.evaluate_resume({"raw": {"run_identity": identity}}, identity)
    assert resumed["action"] == "resume"
    assert helper.evaluate_resume({"raw": {"rows": []}}, identity)["action"] == "refuse"
    refused = helper.evaluate_resume({"raw": {"rows": []}}, identity)
    assert "historical" in " ".join(refused["reasons"]).lower()
    mismatch = helper.evaluate_resume({"raw": {"run_identity": changed}}, identity)
    assert mismatch["action"] == "refuse"
    fresh = helper.evaluate_resume({"raw": None, "candidate": None}, identity)
    assert fresh["action"] == "resume"


# ---------------------------------------------------------------------------
# Tasks 4.2-4.4: summariser must withhold invalid or incomplete verdicts.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows, expected: rows.append(dict(rows[0])),
        lambda rows, expected: rows.__setitem__(0, {**rows[0], "category": "drift"}),
        lambda rows, expected: rows.__setitem__(0, {**rows[0], "latency_s": float("nan")}),
    ],
    ids=["duplicate", "category-drift", "non-finite-latency"],
)
def test_exp26_invalid_cells_have_no_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation
) -> None:
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    gt, plan, manifest, expected = _synthetic_inputs(tmp_path)
    cells = tmp_path / "cells"
    rows = [_row(query_id, category) for query_id, category in expected.items()]
    mutation(rows, expected)
    _write(cells / "raw_none.json", _state(rows))
    _write(cells / "candidate_instruction.json", _state([_row(q, c) for q, c in expected.items()]))
    _configure_exp26(ns, tmp_path, cells, gt, plan, manifest)
    summary = _summary(ns, cells, tmp_path / "report")
    assert summary["status"] == "invalid"
    assert summary.get("verdict") is None


def test_exp26_done_rows_desynchronisation_and_mismatched_pairing_are_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    gt, plan, manifest, expected = _synthetic_inputs(tmp_path, 223)
    cells = tmp_path / "cells"
    first = list(expected.items())[:4]
    second = list(expected.items())[4:8]
    _write(cells / "raw_none.json", _state([_row(q, c) for q, c in first], list(expected)))
    _write(cells / "candidate_instruction.json", _state([_row(q, c) for q, c in second]))
    _configure_exp26(ns, tmp_path, cells, gt, plan, manifest)
    summary = _summary(ns, cells, tmp_path / "report")
    assert summary["status"] == "invalid"
    assert summary.get("verdict") is None


def test_exp26_complete_synthetic_set_evaluates_fail_gates_and_uses_only_out_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    gt, plan, manifest, expected = _synthetic_inputs(tmp_path)
    cells, out = tmp_path / "cells", tmp_path / "report"
    rows = [_row(query_id, category) for query_id, category in expected.items()]
    _write(cells / "raw_none.json", _state(rows))
    _write(cells / "candidate_instruction.json", _state(rows))
    _configure_exp26(ns, tmp_path, cells, gt, plan, manifest)
    summary = _summary(ns, cells, out)
    assert summary["status"] == "complete"
    assert summary["verdict"] == "FAIL"
    assert summary["gates"] and "Negative result" in summary["headline"]
    assert not (ns.EXP_DIR / "results.md").exists()
    assert not (ns.EXP_DIR / "output/eval_results.summary.json").exists()
    assert (out / "eval_results.summary.json").exists()


# ---------------------------------------------------------------------------
# Tasks 4.4-4.5: runner paths, identities and execution-period disclosure.
# ---------------------------------------------------------------------------


def test_exp26_runner_isolates_smoke_and_refuses_historical_measured_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = _load(EXP / "run_eval.py", monkeypatch)
    runner.EXP_DIR = tmp_path / "experiment"
    smoke = runner.resolve_checkpoint_base(limit=4, run_name=None)
    assert smoke == runner.EXP_DIR / "output/smoke/limit-4"
    smoke.mkdir(parents=True)
    with pytest.raises((FileExistsError, SystemExit), match="exists"):
        runner.resolve_checkpoint_base(limit=4, run_name=None)
    legacy = runner.EXP_DIR / "output/cells/raw_none.json"
    _write(legacy, {"rows": [], "done": []})
    with pytest.raises((ValueError, SystemExit), match="historical.*--run-dir"):
        runner.resolve_checkpoint_base(limit=None, run_name=None)
    measured = runner.resolve_checkpoint_base(limit=None, run_name="repair")
    assert measured == runner.EXP_DIR / "output/runs/repair"


def test_exp26_runner_session_state_records_interruptions_and_periods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load(EXP / "run_eval.py", monkeypatch)
    state = runner.new_session_state({"digest": "identity"})
    assert isinstance(state["session_id"], str) and state["periods"] and state["interruptions"] == 0
    resumed = runner.resume_session_state(state)
    assert resumed["interruptions"] == 1 and len(resumed["periods"]) == 2
    assert "not recorded" in runner.execution_periods_text(None).lower()
    assert "single period" in runner.execution_periods_text(state).lower()
    mixed = runner.execution_periods_text(resumed).lower()
    assert "mixed execution periods" in mixed and "shared network epoch" not in mixed


# ---------------------------------------------------------------------------
# Security-review hardening (2026-09-10): unsafe destinations refuse before
# any request path is built.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_name", ["../evil", "/tmp/evil", "nested/name", "..", "."], ids=str)
def test_exp26_runner_rejects_unsafe_run_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_name: str
) -> None:
    runner = _load(EXP / "run_eval.py", monkeypatch)
    runner.EXP_DIR = tmp_path / "experiment"
    with pytest.raises(SystemExit, match="single path component"):
        runner.resolve_checkpoint_base(limit=None, run_name=bad_name)


@pytest.mark.parametrize("bad_limit", [0, -1, -50], ids=str)
def test_exp26_runner_rejects_non_positive_smoke_limits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_limit: int
) -> None:
    """A zero or negative limit must refuse, not silently run every query."""
    runner = _load(EXP / "run_eval.py", monkeypatch)
    runner.EXP_DIR = tmp_path / "experiment"
    with pytest.raises(SystemExit, match="positive integer"):
        runner.resolve_checkpoint_base(limit=bad_limit, run_name=None)


def test_validate_cells_marks_non_object_checkpoints_invalid() -> None:
    helper = _validity()
    expected = _expected()
    good = {
        "rows": [_row(q, c) for q, c in expected.items()],
        "done": list(expected),
    }
    result = helper.validate_cells({"raw": good, "candidate": ["not", "an", "object"]}, expected)
    assert result["status"] == "invalid"
    assert any("not an object" in r for r in result["cells"]["candidate"]["reasons"])


# ---------------------------------------------------------------------------
# Task 4.2: missing checkpoint files produce a clean invalid verdict.
# ---------------------------------------------------------------------------


def test_exp26_missing_checkpoint_file_is_invalid_not_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing checkpoint file must produce an invalid verdict, not a crash."""
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    gt, plan, manifest, expected = _synthetic_inputs(tmp_path)
    cells = tmp_path / "cells"
    cells.mkdir()
    # Write only one of the two required cells.
    rows = [_row(query_id, category) for query_id, category in expected.items()]
    _write(cells / "raw_none.json", _state(rows))
    # candidate_instruction.json is deliberately absent.
    _configure_exp26(ns, tmp_path, cells, gt, plan, manifest)
    summary = _summary(ns, cells, tmp_path / "report")
    assert summary["status"] == "invalid"
    assert summary.get("verdict") is None
    assert "missing" in " ".join(summary["validation"]["pairing_reasons"]).lower()


def test_exp26_negative_latency_is_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A negative latency is structurally invalid and must not produce a verdict."""
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    gt, plan, manifest, expected = _synthetic_inputs(tmp_path)
    cells = tmp_path / "cells"
    rows = [_row(query_id, category) for query_id, category in expected.items()]
    rows[0]["latency_s"] = -0.5
    _write(cells / "raw_none.json", _state(rows))
    _write(cells / "candidate_instruction.json", _state([_row(q, c) for q, c in expected.items()]))
    _configure_exp26(ns, tmp_path, cells, gt, plan, manifest)
    summary = _summary(ns, cells, tmp_path / "report")
    assert summary["status"] == "invalid"
    assert summary.get("verdict") is None


def test_exp26_gate_thresholds_use_full_precision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rounded boundary values must not turn failed gates into passes."""
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    plan = json.loads((EXP / "plan.json").read_text(encoding="utf-8"))
    raw = [{"query_id": "q", "category": "identifier-heavy", "metrics": {"recall_at_5": 0.0}}]
    candidate = [{
        "query_id": "q",
        "category": "identifier-heavy",
        "latency_s": 2.850004,
        "metrics": {"recall_at_5": 0.0299996, "recall_at_10": 0.2582996},
    }]
    rounded = ns._aggregate(candidate)
    exact = ns._aggregate(candidate, rounded=False)
    assert rounded["all"]["p95_latency_ms"] == 2850.0
    assert rounded["identifier-heavy"]["recall_at_10"] == 0.2583
    gates = ns._gates(plan, raw, candidate, exact)
    assert not any(gate["pass"] for gate in gates.values())
    assert gates["latency_p95_ms"]["measured"] > 2850.0
    assert gates["regression_identifier_r10"]["measured"] < 0.2583
