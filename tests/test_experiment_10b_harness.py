"""Fast harness/agreement tests for the Experiment 10b v2 runner (task 4.3.7).

No model, network, Ollama or Chroma: these exercise the pure cell matrix,
the counterbalancing schedule, the audit-visible literal dispatch, the
plan/runner agreement, and the invalid-cell recording contract.  The
digit-leading experiment directory is not importable as a package, so the
runner module is loaded via importlib from its file path.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Any

from experiments._lib import preflight
from experiments._lib.plan import ExperimentPlan

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXPERIMENT_DIR = _REPO_ROOT / "experiments" / "10b-reranker-pool-size-corrected-2026-06-29"
_RUNNER_PATH = _EXPERIMENT_DIR / "run_eval.py"
_PLAN_PATH = _EXPERIMENT_DIR / "plan.json"


def _load_runner() -> Any:
    """Exec the runner module from its path (digit-leading dir)."""
    spec = importlib.util.spec_from_file_location("exp10b_run_eval", _RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["exp10b_run_eval"] = module
    spec.loader.exec_module(module)
    return module


def _search_call_literal_values(source: str, keyword: str) -> set[object]:
    """AST scan mirroring the frozen audit test (defence in depth).

    Collects the literal constant values passed to the given keyword of
    every ``search(...)`` call, bare or attribute, exactly like
    ``tests/test_precalibration_audit_regressions.py``.
    """
    tree = ast.parse(source)
    values: set[object] = set()
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
    """plan.json must describe exactly the cells the runner generates."""
    runner = _load_runner()
    plan = ExperimentPlan.from_json(_PLAN_PATH)
    plan.assert_runner_cells(runner.build_cell_matrix())


def test_exactly_twelve_cells_two_shared_controls() -> None:
    """12 cells: two fetch_k-less shared off-controls plus 10 on-cells."""
    runner = _load_runner()
    cells = runner.build_cell_matrix()
    assert len(cells) == 12
    off_cells = [c for c in cells if not c["factors"]["rerank"]]
    assert {c["id"] for c in off_cells} == {"dense_off", "hybrid_off"}
    assert all("fetch_k" not in c["factors"] for c in off_cells)
    on_cells = [c for c in cells if c["factors"]["rerank"]]
    assert len(on_cells) == 10


def test_fetch_k_pools_declared_distinct() -> None:
    """The 10 on-cells sweep exactly the five declared pools, all distinct.

    Distinctness is asserted per declared pool level: both modes share
    each level by design (dense_on_50 and hybrid_on_50 both map 50), so
    keying by cell id would collide trivially.  Per-mode families are
    asserted too so a within-mode collapse cannot hide.
    """
    runner = _load_runner()
    on_cells = [c for c in runner.build_cell_matrix() if c["factors"]["rerank"]]
    pools = {c["factors"]["fetch_k"] for c in on_cells}
    assert pools == {50, 100, 150, 200, 500}
    for prefix in ("dense", "hybrid"):
        family = {
            c["id"]: c["factors"]["fetch_k"]
            for c in on_cells
            if c["id"].startswith(f"{prefix}_on_")
        }
        assert len(family) == 5
        preflight.assert_distinct_values(family, "retrieval.fetch_k")
    preflight.assert_distinct_values({f"pool_{pool}": pool for pool in pools}, "retrieval.fetch_k")


def test_counterbalanced_order_permutes_all_cells() -> None:
    """Each iteration yields all 12 cells once; iterations differ; deterministic."""
    runner = _load_runner()
    cells = runner.build_cell_matrix()
    expected_ids = sorted(c["id"] for c in cells)
    orders: list[tuple[str, ...]] = []
    for iteration in range(3):
        order = runner.counterbalanced_order(cells, iteration)
        assert sorted(c["id"] for c in order) == expected_ids
        # Deterministic given (cells, iteration): a second call agrees.
        assert [c["id"] for c in runner.counterbalanced_order(cells, iteration)] == [
            c["id"] for c in order
        ]
        orders.append(tuple(c["id"] for c in order))
    assert len(set(orders)) > 1, "iterations 0..2 must not all share one order"


def test_audit_literals_present() -> None:
    """Local mirror of the frozen audit scan: literal sets are exactly False/True."""
    source = _RUNNER_PATH.read_text(encoding="utf-8")
    assert _search_call_literal_values(source, "hybrid") == {False, True}
    assert _search_call_literal_values(source, "rerank") == {False, True}


def test_run_query_dispatch_literals(monkeypatch: Any) -> None:
    """The four (mode, rerank) arms reach the pipeline with the right kwargs."""
    runner = _load_runner()
    import omrg.core.retrieval as retrieval_pkg

    calls: list[dict[str, Any]] = []

    def fake_search(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return []

    # run_query resolves the search entry point from the package at call
    # time, so patching the package attribute redirects the dispatch.
    monkeypatch.setattr(retrieval_pkg, "search", fake_search)

    def _cell(cell_id: str, retrieval: str, rerank: bool, fetch_k: int | None = None) -> dict:
        factors: dict[str, Any] = {"retrieval": retrieval, "rerank": rerank}
        if fetch_k is not None:
            factors["fetch_k"] = fetch_k
        return {"id": cell_id, "factors": factors}

    cases = [
        (_cell("dense_off", "dense", False), False, False, None),
        (_cell("hybrid_off", "hybrid_bm25", False), False, True, None),
        (_cell("dense_on_150", "dense", True, 150), True, False, 150),
        (_cell("hybrid_on_500", "hybrid_bm25", True, 500), True, True, 500),
    ]
    for cell, rerank_expected, hybrid_expected, fetch_expected in cases:
        runner.run_query(
            "probe query",
            top_k=50,
            cell=cell,
            collection_name="c",
            store=None,
            effective_settings=None,
        )
        kwargs = calls[-1]
        assert kwargs["rerank"] is rerank_expected
        assert kwargs["hybrid"] is hybrid_expected
        assert kwargs["similarity_threshold"] == 0.0
        if fetch_expected is None:
            assert "fetch_k" not in kwargs
        else:
            assert kwargs["fetch_k"] == fetch_expected
    assert len(calls) == 4


def test_cell_record_invalid_on_exception() -> None:
    """A raising query runner converts the cell to invalid — no partial data."""
    runner = _load_runner()

    def boom(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("probe failure")

    queries = [{"query_id": "q1", "query": "text", "relevant_parent_ids": [], "nuggets": []}]
    cell = {"id": "dense_off", "factors": {"retrieval": "dense", "rerank": False}}
    record = runner.evaluate_cell(
        cell,
        queries,
        top_k=5,
        collection_name="c",
        store=None,
        effective_settings=None,
        warmup_queries=0,
        run_one=boom,
    )
    assert record["status"] == "invalid"
    assert "probe failure" in record["reason"]
    assert record["cell_id"] == "dense_off"
    assert "per_query" not in record
