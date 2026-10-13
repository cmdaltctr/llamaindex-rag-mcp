"""Run results keep node controls, their sources and node summaries.

A reranker node that disables reranking with an explicit parameter must
bypass inference whatever the inherited default is. The result of
``Engine.run_pipeline`` must record that control, its value and its source,
and each node outcome must carry the node summary (for example
``reranked: false`` and the reason). No model call happens: the reranker is
a fake that fails the test when it is called.
"""

from __future__ import annotations

import asyncio
from typing import Any

from tests.unit.test_engine_pipelines_support import build_engine, rerank_graph

from omrg.core.pipelines import ControlSource, RunStatus


class ForbiddenReranker:
    """A reranker the run must never call."""

    def rerank(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("an explicitly disabled reranker node must not run inference")

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"reranker attribute {name!r} used by a disabled node")


def _run(engine: Any, graph: dict[str, Any]) -> Any:
    return asyncio.run(engine.run_pipeline(graph, inputs={"query": "text"}))


def test_explicit_node_override_is_recorded_with_its_source(effective_settings: Any) -> None:
    """The result names the node control, its value and ``node`` as its source."""
    settings = effective_settings(rerank_enabled=True)
    engine = build_engine(settings, reranker=ForbiddenReranker())
    result = _run(engine, rerank_graph(enabled=False))

    assert result.status is RunStatus.SUCCEEDED, result.error
    control = next(c for c in result.controls["rerank"] if c.lever == "retrieval.rerank_enabled")
    assert control.value is False
    assert control.source is ControlSource.NODE
    assert "rerank" in control.detail
    # Controls of nodes without an override keep their inherited source.
    prepare = {c.lever: c for c in result.controls["prepare"]}
    assert prepare["retrieval.top_k"].source is ControlSource.PROFILE
    engine.close()


def test_inherited_control_records_the_profile_source(effective_settings: Any) -> None:
    """Without a node parameter, the reranker control comes from the profile."""
    engine = build_engine(effective_settings(rerank_enabled=False), reranker=ForbiddenReranker())
    result = _run(engine, rerank_graph())
    control = next(c for c in result.controls["rerank"] if c.lever == "retrieval.rerank_enabled")
    assert (control.value, control.source) == (False, ControlSource.PROFILE)
    engine.close()


def test_node_outcomes_carry_the_node_summary(effective_settings: Any) -> None:
    """A pass-through node explains itself in its stored outcome."""
    engine = build_engine(effective_settings(rerank_enabled=True), reranker=ForbiddenReranker())
    result = _run(engine, rerank_graph(enabled=False))
    outcomes = {outcome.node_id: outcome for outcome in result.nodes}
    rerank = outcomes["rerank"]
    assert rerank.summary["reranked"] is False
    assert rerank.summary["reason"] == "disabled by node parameter"
    assert outcomes["dense"].summary, "every completed node keeps its summary"
    engine.close()


def test_bypassed_node_outcome_keeps_the_bypass_reason(effective_settings: Any) -> None:
    """A node disabled in the graph keeps the bypass reason in its outcome."""
    graph = rerank_graph()
    next(n for n in graph["nodes"] if n["id"] == "rerank")["enabled"] = False
    engine = build_engine(effective_settings(), reranker=ForbiddenReranker())
    result = _run(engine, graph)
    rerank = next(outcome for outcome in result.nodes if outcome.node_id == "rerank")
    assert rerank.status == "bypassed"
    assert rerank.summary["reason"] == "disabled in the graph"
    engine.close()
