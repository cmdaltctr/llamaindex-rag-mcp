"""Fail-before contracts for repair tasks 4.1-4.6 and 5.1, Experiment 27."""

from __future__ import annotations

import json
import os
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
EXP = REPO / "experiments/27-combined-candidate-path-2026-09-09"
EXP22 = REPO / "experiments/22-raw-query-qwen4b-baseline-2026-09-07"
EXP26 = REPO / "experiments/26-query-instruction-ablation-2026-09-08"
GT = EXP22 / "output/ground-truth.json"


class _Module(SimpleNamespace):
    """Expose runpy globals while preserving mutable module constants."""

    def __init__(self, values: dict) -> None:
        super().__init__(**values)
        object.__setattr__(self, "_values", values)

    def __setattr__(self, name: str, value: object) -> None:
        self._values[name] = value
        super().__setattr__(name, value)


def _load(path: Path, monkeypatch: pytest.MonkeyPatch) -> _Module:
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(os, "environ", os.environ.copy())
    values = runpy.run_path(str(path))
    return _Module(values["main"].__globals__)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _copy_checkpoint(source: Path, destination: Path, limit: int | None = None) -> None:
    state = json.loads(source.read_text(encoding="utf-8"))
    if limit is not None:
        state["rows"] = state["rows"][:limit]
        state["done"] = state["done"][:limit]
    _write(destination, state)


def _configure(ns: _Module, root: Path, sources: dict[str, Path]) -> None:
    ns.EXP_DIR = root / "experiment"
    (ns.EXP_DIR / "output").mkdir(parents=True, exist_ok=True)
    ns.GT_PATH = GT
    ns.PLAN_PATH = EXP / "plan.json"
    ns.MANIFEST_PATH = EXP / "output/runtime_manifest.json"
    ns.CELL_SOURCES = sources
    ns._query_token_cost = lambda queries, **kwargs: {
        "available": False, "reason": "offline fixture"
    }
    ns._write_results_md = lambda summary, plan: (root / "rendered.md").write_text(
        summary["headline"], encoding="utf-8"
    )


def _summary(ns: _Module, cells: Path, out_dir: Path) -> dict:
    return ns.summarise_from(cells, out_dir)


def _historical_sources(
    root: Path, combined_limit: int | None = None, instruction_limit: int | None = None
) -> dict[str, Path]:
    cells = root / "cells"
    sources = {
        "baseline_production": EXP22 / "output/cells/hybrid__raw.json",
        "instruction_only": EXP26 / "output/cells/candidate_instruction.json",
        "chunking_only_raw": EXP / "output/cells/chunking_only_raw.json",
        "combined_candidate": EXP / "output/cells/combined_candidate.json",
    }
    copied: dict[str, Path] = {}
    for name, source in sources.items():
        limit = combined_limit if name in {"combined_candidate", "chunking_only_raw"} else None
        if name == "instruction_only" and instruction_limit is not None:
            limit = instruction_limit
        destination = cells / f"{name}.json"
        _copy_checkpoint(source, destination, limit)
        copied[name] = destination
    return copied


# ---------------------------------------------------------------------------
# Task 4.1: a locally paired one-query prefix must never pass the 2x2.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not GT.exists(), reason="untracked ground truth is absent")
def test_one_query_combined_prefix_is_incomplete_and_never_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep both local cells at one row to reach the audited old gate path."""
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    sources = _historical_sources(tmp_path, combined_limit=1)
    _configure(ns, tmp_path, sources)
    summary = _summary(ns, tmp_path / "cells", tmp_path / "report")
    assert summary.get("status") == "incomplete", (
        f"expected INCOMPLETE for one combined query; current verdict={summary.get('verdict')}"
    )
    assert summary.get("verdict") != "PASS"
    assert "promotion" not in (tmp_path / "rendered.md").read_text(encoding="utf-8").lower()


@pytest.mark.skipif(not GT.exists(), reason="untracked ground truth is absent")
def test_loaded_instruction_cell_prefix_invalidates_the_whole_grid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    sources = _historical_sources(tmp_path, instruction_limit=4)
    _configure(ns, tmp_path, sources)
    summary = _summary(ns, tmp_path / "cells", tmp_path / "report")
    assert summary.get("status") == "incomplete"
    assert summary.get("verdict") != "PASS"


@pytest.mark.skipif(not GT.exists(), reason="untracked ground truth is absent")
def test_all_four_cells_must_have_identical_query_id_sets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    sources = _historical_sources(tmp_path)
    state = json.loads(sources["combined_candidate"].read_text(encoding="utf-8"))
    state["rows"][0]["query_id"] = "foreign-id"
    state["done"][0] = "foreign-id"
    _write(sources["combined_candidate"], state)
    _configure(ns, tmp_path, sources)
    summary = _summary(ns, tmp_path / "cells", tmp_path / "report")
    assert summary.get("status") == "invalid"
    assert summary.get("verdict") is None


# ---------------------------------------------------------------------------
# Tasks 4.4-4.5: Experiment 27 runner checkpoint and session contracts.
# ---------------------------------------------------------------------------


def test_exp27_runner_uses_isolated_smoke_and_named_measured_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = _load(EXP / "run_eval.py", monkeypatch)
    runner.EXP_DIR = tmp_path / "experiment"
    smoke = runner.resolve_checkpoint_base(limit=1, run_name=None)
    assert smoke == runner.EXP_DIR / "output/smoke/limit-1"
    smoke.mkdir(parents=True)
    with pytest.raises((FileExistsError, SystemExit), match="exists"):
        runner.resolve_checkpoint_base(limit=1, run_name=None)
    _write(runner.EXP_DIR / "output/cells/combined_candidate.json", {"rows": [], "done": []})
    with pytest.raises((ValueError, SystemExit), match="historical.*--run-dir"):
        runner.resolve_checkpoint_base(limit=None, run_name=None)
    measured = runner.resolve_checkpoint_base(limit=None, run_name="measured")
    assert measured == runner.EXP_DIR / "output/runs/measured"


def test_exp27_runner_session_provenance_cannot_claim_one_network_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load(EXP / "run_eval.py", monkeypatch)
    state = runner.new_session_state({"digest": "identity"})
    assert isinstance(state["session_id"], str) and len(state["periods"]) == 1
    resumed = runner.resume_session_state(state)
    assert resumed["interruptions"] == 1 and len(resumed["periods"]) == 2
    assert "not recorded" in runner.execution_periods_text(None).lower()
    assert "single period" in runner.execution_periods_text(state).lower()
    text = runner.execution_periods_text(resumed).lower()
    assert "mixed execution periods" in text and "shared network epoch" not in text


# ---------------------------------------------------------------------------
# Security-review hardening (2026-09-10): unsafe destinations refuse before
# any request path is built.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_name", ["../evil", "/tmp/evil", "a/b"], ids=str)
def test_exp27_runner_rejects_unsafe_run_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_name: str
) -> None:
    runner = _load(EXP / "run_eval.py", monkeypatch)
    runner.EXP_DIR = tmp_path / "experiment"
    with pytest.raises(SystemExit, match="single path component"):
        runner.resolve_checkpoint_base(limit=None, run_name=bad_name)


@pytest.mark.parametrize("bad_limit", [0, -2], ids=str)
def test_exp27_runner_rejects_non_positive_smoke_limits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_limit: int
) -> None:
    """A zero or negative limit must refuse, not silently run every query."""
    runner = _load(EXP / "run_eval.py", monkeypatch)
    runner.EXP_DIR = tmp_path / "experiment"
    with pytest.raises(SystemExit, match="positive integer"):
        runner.resolve_checkpoint_base(limit=bad_limit, run_name=None)


# ---------------------------------------------------------------------------
# Task 4.2: missing checkpoint files produce a clean invalid verdict.
# ---------------------------------------------------------------------------


def _synthetic_sources(ns: _Module, root: Path) -> dict[str, Path]:
    """Build a complete grid without ignored ground truth or paid artefacts."""
    query = {
        "query_id": "q",
        "query": "synthetic query",
        "category": "identifier-heavy",
        "relevant_parent_ids": ["hit"],
        "nuggets": [],
    }
    row = {
        "query_id": "q", "category": "identifier-heavy", "parent_ids": ["miss"], "latency_s": 0.1
    }
    sources = {
        cell: _write(root / "historical/cells" / f"{cell}.json", {"rows": [row], "done": ["q"]})
        for cell in ns.CELL_SOURCES
    }
    _configure(ns, root, sources)
    ns.GT_PATH = _write(root / "ground-truth.json", {"queries": [query]})
    ns.MANIFEST_PATH = _write(root / "runtime_manifest.json", {"embedding": {}})
    return sources


def test_exp27_missing_measured_cell_is_invalid_not_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Intact historical cells cannot fill gaps in a separately requested run."""
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    sources = _synthetic_sources(ns, tmp_path)
    cells = tmp_path / "requested/cells"
    # Both requested cells are absent, but both historical fallbacks exist.
    empty = _summary(ns, cells, tmp_path / "empty-report")
    assert empty["status"] == "invalid" and empty["verdict"] is None
    _copy_checkpoint(sources["chunking_only_raw"], cells / "chunking_only_raw.json")
    summary = _summary(ns, cells, tmp_path / "partial-report")
    assert summary["status"] == "invalid" and summary["verdict"] is None
    assert "different query id sets" in " ".join(summary["validation"]["pairing_reasons"])
    assert summary["cell_sources"]["combined_candidate"] == str(cells / "combined_candidate.json")
    assert sources["combined_candidate"].exists()


def test_exp27_negative_latency_is_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A negative latency in any cell invalidates the whole grid."""
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    sources = _synthetic_sources(ns, tmp_path)
    state = json.loads(sources["combined_candidate"].read_text(encoding="utf-8"))
    state["rows"][0]["latency_s"] = -1.0
    _write(sources["combined_candidate"], state)
    summary = ns.summarise_from(None, tmp_path / "report")
    assert summary["status"] == "invalid" and summary["verdict"] is None


def test_exp27_gates_use_unrounded_aggregates(monkeypatch: pytest.MonkeyPatch) -> None:
    """All three combined gates reject values rounded onto their thresholds."""
    ns = _load(EXP / "summarise_eval.py", monkeypatch)
    plan = json.loads((EXP / "plan.json").read_text(encoding="utf-8"))
    rows = [{
        "category": "identifier-heavy",
        "latency_s": 2.850004,
        "metrics": {"recall_at_5": 0.2309996, "recall_at_10": 0.2582996},
    }]
    rounded = ns._aggregate(rows)
    assert all(gate["pass"] for gate in ns._gates(plan, rounded).values())
    exact = ns._aggregate(rows, rounded=False)
    assert not any(gate["pass"] for gate in ns._gates(plan, exact).values())
