"""Fast harness tests for the repaired Experiment 13 runner (task 4.3.5).

No models, network, Ollama or Chroma: the runner is loaded via importlib
(the experiment directory name starts with a digit) and only its pure
functions plus the monkeypatched search dispatch are exercised, per
design D15 (protocol/runner agreement without expensive models).
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Any

from experiments._lib.plan import ExperimentPlan

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXP13_DIR = _REPO_ROOT / "experiments" / "13-hard-technical-threshold-calibration-2026-06-29"

_spec = importlib.util.spec_from_file_location("exp13_run_eval", _EXP13_DIR / "run_eval.py")
assert _spec is not None and _spec.loader is not None
exp13 = importlib.util.module_from_spec(_spec)
sys.modules["exp13_run_eval"] = exp13
_spec.loader.exec_module(exp13)


def _search_call_literal_values(source: str, keyword: str) -> set[Any]:
    """Return literal values passed to ``search(..., keyword=...)`` calls.

    Local copy of the frozen audit helper in
    ``tests/test_precalibration_audit_regressions.py`` — that file is
    frozen, so this harness test carries its own scanner.
    """
    tree = ast.parse(source)
    values: set[Any] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "search":
            continue
        for item in node.keywords:
            if item.arg != keyword:
                continue
            if isinstance(item.value, ast.Constant):
                values.add(item.value.value)
            elif isinstance(item.value, ast.Name) and item.value.id == "None":
                values.add(None)
    return values


def test_plan_agrees_with_runner_cell_matrix() -> None:
    """plan.json (D15) must enumerate exactly the runner's 42 cells."""
    plan = ExperimentPlan.from_json(_EXP13_DIR / "plan.json")
    plan.assert_runner_cells(exp13.build_cell_matrix())


def test_forty_two_cells_with_twelve_references() -> None:
    """42 cells: 30 policy, 12 threshold-free reference envelope cells."""
    cells = exp13.build_cell_matrix()

    assert len(cells) == 42
    references = [c for c in cells if c["factors"]["arm"] != "policy"]
    policy = [c for c in cells if c["factors"]["arm"] == "policy"]
    assert len(references) == 12
    assert len(policy) == 30
    assert all("threshold" not in c["factors"] for c in references)
    assert all(c["factors"]["threshold"] in exp13.THRESHOLDS for c in policy)
    assert len({c["id"] for c in cells}) == 42


def test_fixed_blocks_are_paired_across_thresholds() -> None:
    """Same fraction -> identical block on every call; blocks differ by mix.

    ``build_fixed_blocks`` seeds a private ``random.Random`` per fraction
    with ``f"{seed}:{fraction}"``, so repeated calls (and fresh process
    runs with the same seed) reproduce the same block for a fraction, and
    fractions with different compositions draw different query sets.
    """
    technical = [
        {"id": f"t{i}", "text": f"technical query {i}", "query_type": "technical"}
        for i in range(40)
    ]
    semantic = [
        {"id": f"s{i}", "text": f"semantic query {i}", "query_type": "semantic"} for i in range(40)
    ]
    fractions = [1.0, 0.5, 0.0]

    first = exp13.build_fixed_blocks(technical, semantic, fractions, seed=exp13.SEED)
    second = exp13.build_fixed_blocks(technical, semantic, fractions, seed=exp13.SEED)

    assert first == second, "same seed and fraction must reproduce the same block"
    assert all(q["query_type"] == "technical" for q in first[1.0])
    assert all(q["query_type"] == "semantic" for q in first[0.0])
    assert {q["id"] for q in first[0.5]} != {q["id"] for q in first[1.0]}


def test_audit_literal_rerank_none_present() -> None:
    """Policy arm must pass a literal rerank=None; references False/True."""
    source = (_EXP13_DIR / "run_eval.py").read_text(encoding="utf-8")
    rerank_values = _search_call_literal_values(source, "rerank")

    assert None in rerank_values
    assert {False, True} <= rerank_values


def test_run_query_dispatch_arms(monkeypatch) -> None:
    """run_query forwards literal rerank tri-state and settings per arm."""
    import rag_mcp.core.retrieval as retrieval_pkg
    from rag_mcp.core.settings import EffectiveSettings

    calls: list[dict[str, Any]] = []

    def fake_search(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [{"id": "doc-1", "score": 0.5}]

    monkeypatch.setattr(retrieval_pkg, "search", fake_search)

    effective = EffectiveSettings()
    for arm, expected in (("policy", None), ("reranker_off", False), ("reranker_on", True)):
        calls.clear()
        results = exp13.run_query(
            "query text",
            arm=arm,
            collection_name="exp13-collection",
            store=object(),
            effective=effective,
            top_k=5,
        )
        assert results == [{"id": "doc-1", "score": 0.5}]
        assert len(calls) == 1
        assert calls[0]["rerank"] is expected
        assert calls[0]["effective_settings"] is effective
        assert calls[0]["hybrid"] is False
        assert calls[0]["top_k"] == 5
        assert calls[0]["collection_name"] == "exp13-collection"


def test_policy_cell_settings_carry_threshold() -> None:
    """threshold_effective_settings overlays the swept level, base intact."""
    from rag_mcp.core.settings import EffectiveSettings

    base = EffectiveSettings()
    effective = exp13.threshold_effective_settings(base, 0.5)

    assert effective.retrieval.hard_technical_threshold == 0.5
    assert effective is not base
    default_threshold = EffectiveSettings().retrieval.hard_technical_threshold
    assert base.retrieval.hard_technical_threshold == default_threshold
