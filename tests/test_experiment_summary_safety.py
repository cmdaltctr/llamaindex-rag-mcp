"""Synthetic preservation and provenance regressions for experiments 26 and 27."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXPERIMENTS = {
    26: "26-query-instruction-ablation-2026-09-08",
    27: "27-combined-candidate-path-2026-09-09",
}


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _fixture(number: int, root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, dict]:
    """Load the actual report writer with synthetic checkpoints and no services."""
    experiment = REPO / "experiments" / EXPERIMENTS[number]
    monkeypatch.syspath_prepend(str(experiment))
    monkeypatch.syspath_prepend(str(REPO / "experiments"))
    values = runpy.run_path(str(experiment / "summarise_eval.py"))
    ns = values["summarise_from"].__globals__
    ns["EXP_DIR"] = root / "experiment"
    ns["EXP_DIR"].mkdir()
    query = {
        "query_id": "q",
        "query": "synthetic query",
        "category": "identifier-heavy",
        "relevant_parent_ids": ["hit"],
        "nuggets": [],
    }
    ns["GT_PATH"] = _write(root / "ground-truth.json", {"queries": [query]})
    ns["PLAN_PATH"] = _write(
        root / "plan.json", json.loads((experiment / "plan.json").read_text(encoding="utf-8"))
    )
    ns["MANIFEST_PATH"] = _write(
        root / "historical/runtime_manifest.json",
        {"embedding": {"candidate_instruction": "historical instruction"}},
    )
    cells = ns["CELLS"] if number == 26 else tuple(ns["CELL_SOURCES"])
    state = {
        "rows": [{
            "query_id": "q", "category": "identifier-heavy",
            "parent_ids": ["miss"], "latency_s": 0.1,
        }],
        "done": ["q"],
    }
    sources = {cell: _write(root / "cells" / f"{cell}.json", state) for cell in cells}
    if number == 26:
        ns["BASELINE_CKPT"] = sources["raw_none"]
        ns["BOOTSTRAP_N"] = 100
    else:
        ns["CELL_SOURCES"] = sources
        ns["_drift"] = lambda aggregates: {"available": False, "reason": "synthetic fixture"}
        ns["_query_token_cost"] = lambda queries, **kwargs: {
            "available": False, "reason": "synthetic fixture"
        }
    return ns, sources


@pytest.mark.parametrize("number", [26, 27])
@pytest.mark.parametrize("invalid", [False, True])
def test_summaries_preserve_existing_evidence(
    number: int, invalid: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ns, sources = _fixture(number, tmp_path, monkeypatch)
    if invalid:
        sources[next(iter(sources))].unlink()
    out = tmp_path / "report"
    summary = ns["summarise_from"](tmp_path / "cells", out)
    assert summary["status"] == ("invalid" if invalid else "complete")
    before = {path.name: path.read_bytes() for path in out.iterdir()}
    assert set(before) == {"eval_results.summary.json", "results.md"}
    assert not list(out.glob("*.tmp"))
    with pytest.raises(FileExistsError):
        ns["summarise_from"](tmp_path / "cells", out)
    assert {path.name: path.read_bytes() for path in out.iterdir()} == before

    frozen = ns["EXP_DIR"] / "results.md"
    frozen.write_text("historical evidence", encoding="utf-8")
    with pytest.raises(FileExistsError):
        ns["summarise_from"](tmp_path / "cells", ns["EXP_DIR"])
    assert frozen.read_text(encoding="utf-8") == "historical evidence"


def test_report_paths_refuse_symlinks_and_checkpoint_descendants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(REPO / "experiments"))
    from _lib.checkpoint_validity import create_report_directory, write_report_text

    inputs = tmp_path / "cells"
    inputs.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(inputs, target_is_directory=True)
    with pytest.raises(ValueError):
        create_report_directory(alias, [inputs])
    with pytest.raises(ValueError):
        create_report_directory(alias / "report", [inputs])
    assert not (inputs / "report").exists()

    dangling = tmp_path / "dangling"
    target = tmp_path / "absent"
    dangling.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        create_report_directory(dangling, [inputs])
    assert not target.exists()

    out = create_report_directory(tmp_path / "output/runs/new/report", [inputs])
    evidence = inputs / "evidence.json"
    evidence.write_text("preserved", encoding="utf-8")
    link = out / "eval_results.summary.json"
    link.symlink_to(evidence)
    with pytest.raises(FileExistsError):
        write_report_text(link, "replacement")
    assert evidence.read_text(encoding="utf-8") == "preserved"


@pytest.mark.parametrize("number", [26, 27])
@pytest.mark.parametrize("malformed", ["null-rows", "unhashable-id", "invalid-json"])
def test_malformed_checkpoints_produce_invalid_reports(
    number: int, malformed: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ns, sources = _fixture(number, tmp_path, monkeypatch)
    path = sources[next(iter(sources))]
    if malformed == "invalid-json":
        path.write_text("{", encoding="utf-8")
    else:
        state = json.loads(path.read_text(encoding="utf-8"))
        if malformed == "null-rows":
            state["rows"] = None
        else:
            state["rows"][0]["query_id"] = ["not", "a", "string"]
        _write(path, state)
    result = ns["summarise_from"](tmp_path / "cells", tmp_path / "report")
    assert result["status"] == "invalid" and result["verdict"] is None
    assert result["validation"]["cells"][next(iter(sources))]["reasons"]


def _record_session(ns: dict, sources: dict, root: Path, number: int) -> dict:
    """Create matching session evidence using the runner's existing hash contract."""
    from _lib.checkpoint_validity import run_identity

    manifest = {"embedding": {"candidate_instruction": "recorded run instruction"}}
    _write(root / "runtime_manifest.json", manifest)
    corpus = _write(root / "corpus.json", {"synthetic": True})
    code = root / "runner.py"
    code.write_text("# synthetic runner", encoding="utf-8")
    identity = run_identity(ns["PLAN_PATH"], ns["GT_PATH"], corpus, manifest, [code])
    session = {
        "session_id": "synthetic-session",
        "run_identity": identity,
        "periods": [{"started_utc": "2026-09-10T00:00:00Z", "ended_utc": "2026-09-10T00:00:01Z"}],
        "interruptions": 0,
    }
    _write(root / "session.json", session)
    measured = ns["CELLS"] if number == 26 else ns["MEASURED_HERE"]
    for cell in measured:
        state = json.loads(sources[cell].read_text(encoding="utf-8"))
        state.update(run_identity=identity, session_id=session["session_id"])
        _write(sources[cell], state)
    return session


@pytest.mark.parametrize("number", [26, 27])
@pytest.mark.parametrize(
    "mutation", ["run-identity", "session-id", "manifest", "legacy-with-session"]
)
def test_mismatched_session_inputs_cannot_produce_a_verdict(
    number: int, mutation: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ns, sources = _fixture(number, tmp_path, monkeypatch)
    _record_session(ns, sources, tmp_path, number)
    cell = ns["CELLS"][0] if number == 26 else ns["MEASURED_HERE"][0]
    state = json.loads(sources[cell].read_text(encoding="utf-8"))
    if mutation == "run-identity":
        state["run_identity"] = {**state["run_identity"], "plan": "different"}
    elif mutation == "session-id":
        state["session_id"] = "different-session"
    elif mutation == "legacy-with-session":
        state.pop("run_identity")
        state.pop("session_id")
    else:
        _write(
            tmp_path / "runtime_manifest.json", {"embedding": {"candidate_instruction": "changed"}}
        )
    _write(sources[cell], state)
    result = ns["summarise_from"](tmp_path / "cells", tmp_path / "report")
    assert result["status"] == "invalid" and result["verdict"] is None
    assert result["validation"]["pairing_reasons"]


@pytest.mark.parametrize("number", [26, 27])
def test_matched_session_uses_its_own_manifest_and_preserves_inputs(
    number: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ns, sources = _fixture(number, tmp_path, monkeypatch)
    session = _record_session(ns, sources, tmp_path, number)
    before = {cell: path.read_bytes() for cell, path in sources.items()}
    result = ns["summarise_from"](tmp_path / "cells", tmp_path / "report")
    assert result["status"] == "complete"
    assert result["execution"]["session"] == session
    assert not result["provenance"]["historical"]
    assert (
        result["runtime_manifest"]["embedding"]["candidate_instruction"]
        == "recorded run instruction"
    )
    assert {cell: path.read_bytes() for cell, path in sources.items()} == before
    if number == 27:
        assert any("Reference cells" in limit for limit in result["provenance"]["limits"])
