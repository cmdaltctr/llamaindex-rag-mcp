"""Tasks 4.1 and 4.2: ready-node scheduling, joins, fan-out, limits and events."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import BaseModel
from tests.unit.test_pipeline_runner_support import (
    Recorder,
    Script,
    admit,
    query_graph,
    scripted_catalogue,
)
from tests.unit.test_pipeline_support import search_graph

from omrg.core.pipelines import (
    EventKind,
    NodeContext,
    NodeOutput,
    NodeStatus,
    RunLimits,
    RunStatus,
    run_pipeline,
)

HYBRID = query_graph(
    [("dense", "retrieve.dense"), ("sparse", "retrieve.sparse"), ("fuse", "combine.rrf")],
    [("dense.evidence", "fuse.ranked"), ("sparse.evidence", "fuse.ranked")],
    ["dense.query", "sparse.query"],
    {"evidence": "fuse.evidence"},
)

FAN_OUT = query_graph(
    [
        ("dense", "retrieve.dense"),
        ("r1", "select.rerank"),
        ("r2", "select.rerank"),
        ("fuse", "combine.rrf"),
    ],
    [
        ("dense.evidence", "r1.evidence"),
        ("dense.evidence", "r2.evidence"),
        ("r1.evidence", "fuse.ranked"),
        ("r2.evidence", "fuse.ranked"),
    ],
    ["dense.query"],
    {"evidence": "fuse.evidence", "dense": "dense.evidence"},
)

RESOURCES = {"store": object(), "embedder": object(), "reranker": object()}


async def _run(snapshot: Any, script: Script, **kwargs: Any):
    return await run_pipeline(snapshot, scripted_catalogue(script), RESOURCES, **kwargs)


@pytest.mark.parametrize("first", ["dense", "sparse"])
async def test_join_order_is_declared_order_not_completion_order(
    first: str, effective_settings: Any
) -> None:
    """Both completion orders give the join the same ordered inputs."""
    script = Script()
    finished: list[str] = []
    first_done = asyncio.Event()
    second = "sparse" if first == "dense" else "dense"

    async def finish_first(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        finished.append(ctx.node_id)
        first_done.set()
        return NodeOutput(values={"evidence": [f"{ctx.node_id}-hit"]})

    async def finish_second(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await first_done.wait()
        finished.append(ctx.node_id)
        return NodeOutput(values={"evidence": [f"{ctx.node_id}-hit"]})

    script.on(first, finish_first)
    script.on(second, finish_second)
    result = await _run(admit(HYBRID, effective_settings, {"query": "q"}), script)

    assert result.status is RunStatus.SUCCEEDED
    assert finished == [first, second]
    assert script.inputs["fuse"] == [{"ranked": (["dense-hit"], ["sparse-hit"])}]
    assert result.outputs == {"evidence": "fuse.evidence"}


async def test_empty_branch_is_valid_join_input(effective_settings: Any) -> None:
    """An empty dense list joins a sparse result; it is not a missing input."""
    script = Script()

    async def empty(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        return NodeOutput(values={"evidence": []})

    script.on("dense", empty)
    result = await _run(admit(HYBRID, effective_settings, {"query": "q"}), script)
    assert result.status is RunStatus.SUCCEEDED
    assert script.inputs["fuse"] == [{"ranked": ([], "sparse.evidence")}]


async def test_fan_out_isolates_mutable_values(effective_settings: Any) -> None:
    """Each consumer and the graph output get their own copy of a list."""
    script = Script()
    seen: dict[str, list[str]] = {}
    received: dict[str, int] = {}

    async def produce(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        return NodeOutput(values={"evidence": ["a"]})

    async def mutate(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        evidence = inputs["evidence"]
        seen[ctx.node_id] = list(evidence)
        received[ctx.node_id] = id(evidence)
        evidence.append(ctx.node_id)
        return NodeOutput(values={"evidence": evidence})

    script.on("dense", produce)
    script.on("r1", mutate)
    script.on("r2", mutate)
    result = await _run(admit(FAN_OUT, effective_settings, {"query": "q"}), script)

    assert result.status is RunStatus.SUCCEEDED
    assert seen == {"r1": ["a"], "r2": ["a"]}
    assert received["r1"] != received["r2"]
    assert result.outputs["dense"] == ["a"]
    assert script.inputs["fuse"] == [{"ranked": (["a", "r1"], ["a", "r2"])}]


async def test_ready_nodes_wait_for_the_concurrency_bound(effective_settings: Any) -> None:
    """With a bound of two, the third ready branch waits for a free slot."""
    data = query_graph(
        [(n, "retrieve.dense") for n in ("d1", "d2", "d3")] + [("fuse", "combine.rrf")],
        [(f"{n}.evidence", "fuse.ranked") for n in ("d1", "d2", "d3")],
        ["d1.query", "d2.query", "d3.query"],
        {"evidence": "fuse.evidence"},
    )
    script = Script()
    gates = {n: asyncio.Event() for n in ("d1", "d2", "d3")}

    async def gated(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await gates[ctx.node_id].wait()
        return NodeOutput(values={"evidence": [ctx.node_id]})

    for node in gates:
        script.on(node, gated)
    recorder = Recorder()
    task = asyncio.create_task(
        _run(admit(data, effective_settings, {"query": "q"}), script, on_event=recorder)
    )
    await script.started["d1"].wait()
    await script.started["d2"].wait()
    await asyncio.sleep(0)
    assert not script.started["d3"].is_set()
    assert script.running == 2

    gates["d1"].set()
    await script.started["d3"].wait()
    gates["d2"].set()
    gates["d3"].set()
    result = await task

    assert result.status is RunStatus.SUCCEEDED
    assert script.peak == 2
    assert recorder.index(EventKind.NODE_QUEUED, "d3") < recorder.index(
        EventKind.NODE_COMPLETED, "d1"
    )
    assert recorder.index(EventKind.NODE_COMPLETED, "d1") < recorder.index(
        EventKind.NODE_STARTED, "d3"
    )
    assert script.inputs["fuse"] == [{"ranked": (["d1"], ["d2"], ["d3"])}]


async def test_model_calls_on_one_resource_are_serialised(effective_settings: Any) -> None:
    """Two reranker nodes never overlap under the default lease rules."""
    script = Script()
    gate = asyncio.Event()

    async def gated(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await gate.wait()
        return NodeOutput(values={"evidence": [ctx.node_id]})

    script.on("r1", gated)
    script.on("r2", gated)
    task = asyncio.create_task(_run(admit(FAN_OUT, effective_settings, {"query": "q"}), script))
    await script.started["r1"].wait()
    await asyncio.sleep(0)
    assert not script.started["r2"].is_set()
    gate.set()
    result = await task
    assert result.status is RunStatus.SUCCEEDED
    assert script.peak == 1


async def test_lease_rules_are_configurable(effective_settings: Any) -> None:
    """Without exclusive effects, both reranker branches run together."""
    script = Script()
    gate = asyncio.Event()

    async def gated(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await gate.wait()
        return NodeOutput(values={"evidence": [ctx.node_id]})

    script.on("r1", gated)
    script.on("r2", gated)
    limits = RunLimits(max_concurrency=2, exclusive_effects=frozenset())
    task = asyncio.create_task(
        _run(admit(FAN_OUT, effective_settings, {"query": "q"}), script, limits=limits)
    )
    await script.started["r1"].wait()
    await script.started["r2"].wait()
    gate.set()
    assert (await task).status is RunStatus.SUCCEEDED
    assert script.peak == 2


def test_limits_reject_a_zero_bound() -> None:
    """A concurrency bound below one is a configuration error."""
    with pytest.raises(ValueError, match="max_concurrency"):
        RunLimits(max_concurrency=0)


async def test_node_failure_skips_dependants_and_names_the_node(effective_settings: Any) -> None:
    """A failed branch skips its dependants; an independent branch still runs."""
    script = Script()

    async def broken(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        raise RuntimeError("index offline")

    script.on("dense", broken)
    recorder = Recorder()
    snapshot = admit(search_graph(), effective_settings, {"query": "q"})
    result = await run_pipeline(
        snapshot,
        scripted_catalogue(script),
        {**RESOURCES, "completion": object()},
        on_event=recorder,
    )

    assert result.status is RunStatus.FAILED
    assert result.failed_node == "dense"
    assert "index offline" in (result.error or "")
    assert set(result.skipped_nodes) == {"fuse", "rerank", "context", "answer"}
    statuses = {n.node_id: n.status for n in result.nodes}
    assert statuses["sparse"] is NodeStatus.SUCCEEDED
    assert not script.called("fuse")
    assert result.outputs == {}
    assert recorder.kinds()[-1] is EventKind.RUN_FAILED
    assert EventKind.NODE_SKIPPED in recorder.kinds("answer")


async def test_domain_fallback_is_an_outcome_not_a_failure(effective_settings: Any) -> None:
    """An adapter fallback is reported with its reason; the run succeeds."""
    script = Script()

    async def degraded(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        return NodeOutput(
            values={"evidence": inputs["evidence"]}, fallback="reranker model is not available"
        )

    script.on("rerank", degraded)
    recorder = Recorder()
    snapshot = admit(search_graph(), effective_settings, {"query": "q"})
    result = await run_pipeline(
        snapshot,
        scripted_catalogue(script),
        {**RESOURCES, "completion": object()},
        on_event=recorder,
    )

    assert result.status is RunStatus.SUCCEEDED
    rerank = next(n for n in result.nodes if n.node_id == "rerank")
    assert rerank.status is NodeStatus.SUCCEEDED
    assert rerank.fallback == "reranker model is not available"
    kinds = recorder.kinds("rerank")
    assert kinds.index(EventKind.NODE_FALLBACK) < kinds.index(EventKind.NODE_COMPLETED)
    assert EventKind.NODE_FAILED not in recorder.kinds()


async def test_events_are_ordered_actual_transitions(effective_settings: Any) -> None:
    """Sequences increase by one; each node is queued, started, then completed."""
    recorder = Recorder()
    result = await _run(
        admit(HYBRID, effective_settings, {"query": "q"}), Script(), on_event=recorder
    )
    events = recorder.events
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))
    assert {e.run_id for e in events} == {result.run_id}
    assert events[0].kind is EventKind.RUN_STARTED
    assert events[-1].kind is EventKind.RUN_COMPLETED
    for node in ("dense", "sparse", "fuse"):
        assert recorder.kinds(node) == [
            EventKind.NODE_QUEUED,
            EventKind.NODE_STARTED,
            EventKind.NODE_COMPLETED,
        ]
    assert all(e.unit_id is None for e in events)


async def test_disabled_node_forwards_its_bypass_value(effective_settings: Any) -> None:
    """A disabled reranker is bypassed without calling its adapter."""
    data = search_graph()
    data["nodes"][3]["enabled"] = False
    recorder = Recorder()
    script = Script()
    snapshot = admit(data, effective_settings, {"query": "q"})
    result = await run_pipeline(
        snapshot,
        scripted_catalogue(script),
        {**RESOURCES, "completion": object()},
        on_event=recorder,
    )
    assert result.status is RunStatus.SUCCEEDED
    assert not script.called("rerank")
    assert script.inputs["context"] == [{"evidence": "fuse.evidence"}]
    assert recorder.kinds("rerank") == [EventKind.NODE_BYPASSED]
    assert next(n for n in result.nodes if n.node_id == "rerank").status is NodeStatus.BYPASSED


async def test_wall_time_is_measured_not_summed(effective_settings: Any) -> None:
    """Two overlapping nodes keep their own durations; wall time is end to end."""
    now = [0.0]
    script = Script()
    gate = asyncio.Event()

    async def slow(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await gate.wait()
        return NodeOutput(values={"evidence": []})

    async def advance(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await script.started["dense"].wait()
        now[0] = 10.0
        gate.set()
        return NodeOutput(values={"evidence": []})

    async def fuse(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        return NodeOutput(values={"evidence": []})

    script.on("dense", slow)
    script.on("sparse", advance)
    script.on("fuse", fuse)
    result = await _run(
        admit(HYBRID, effective_settings, {"query": "q"}), script, clock=lambda: now[0]
    )
    durations = {n.node_id: n.duration_s for n in result.nodes}
    assert durations == {"dense": 10.0, "sparse": 10.0, "fuse": 0.0}
    assert result.wall_time_s == 10.0
