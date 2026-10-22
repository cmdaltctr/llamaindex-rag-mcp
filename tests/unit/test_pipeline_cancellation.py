"""Task 4.4: run-scoped cooperative cancellation."""

from __future__ import annotations

import asyncio
import threading
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
from tests.unit.test_pipeline_support import ingest_graph

from omrs.core.pipelines import (
    CancellationFlag,
    EventKind,
    NodeContext,
    NodeOutput,
    NodeStatus,
    PipelineCancelledError,
    RunCancellation,
    RunLimits,
    RunStatus,
    UnitSplit,
    run_pipeline,
)

RESOURCES = {"store": object(), "embedder": object(), "reranker": object()}
HYBRID = query_graph(
    [("dense", "retrieve.dense"), ("sparse", "retrieve.sparse"), ("fuse", "combine.rrf")],
    [("dense.evidence", "fuse.ranked"), ("sparse.evidence", "fuse.ranked")],
    ["dense.query", "sparse.query"],
    {"evidence": "fuse.evidence"},
)


def _statuses(result: Any) -> dict[str, NodeStatus]:
    return {n.node_id: n.status for n in result.nodes}


def _committing_script(gate: asyncio.Event | None = None) -> Script:
    script = Script()

    async def commit(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        if gate is not None:
            await gate.wait()
        return NodeOutput(values={"summary": {}}, effects=(f"committed:{ctx.unit_id}",))

    script.on("commit", commit)
    return script


async def test_queued_nodes_are_cancelled(effective_settings: Any) -> None:
    """A queued branch never starts; the running branch finishes honestly."""
    script = Script()
    gate = asyncio.Event()

    async def gated(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await gate.wait()
        return NodeOutput(values={"evidence": []})

    script.on("dense", gated)
    token = RunCancellation()
    recorder = Recorder()
    task = asyncio.create_task(
        run_pipeline(
            admit(HYBRID, effective_settings, {"query": "q"}),
            scripted_catalogue(script),
            RESOURCES,
            on_event=recorder,
            cancellation=token,
            limits=RunLimits(max_concurrency=1),
        )
    )
    await script.started["dense"].wait()
    token.cancel("user request")
    await recorder.wait_for(EventKind.RUN_CANCELLING)
    assert not task.done()
    gate.set()
    result = await task

    assert result.status is RunStatus.CANCELLED
    assert _statuses(result) == {
        "dense": NodeStatus.SUCCEEDED,
        "sparse": NodeStatus.CANCELLED,
        "fuse": NodeStatus.CANCELLED,
    }
    assert not script.called("sparse")
    assert recorder.kinds("sparse") == [EventKind.NODE_QUEUED, EventKind.NODE_CANCELLED]
    assert recorder.kinds()[-1] is EventKind.RUN_CANCELLED


async def test_cancellation_before_commit_prevents_the_commit(effective_settings: Any) -> None:
    """A request that arrives before the commit starts stops the commit."""
    script = _committing_script()
    token = RunCancellation()

    async def embed(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        token.cancel()
        return NodeOutput(values={"chunks": ["vector"]})

    script.on("embed", embed)
    result = await run_pipeline(
        admit(ingest_graph(), effective_settings, {"path": "a.md"}),
        scripted_catalogue(script),
        RESOURCES,
        cancellation=token,
    )
    assert result.status is RunStatus.CANCELLED
    assert not script.called("commit")
    assert _statuses(result)["embed"] is NodeStatus.SUCCEEDED
    assert _statuses(result)["commit"] is NodeStatus.CANCELLED
    assert result.completed_effects == ()


async def test_entered_commit_completes_before_terminal_cancel(effective_settings: Any) -> None:
    """A commit that has started finishes; the result discloses it."""
    gate = asyncio.Event()
    script = _committing_script(gate)
    token = RunCancellation()
    recorder = Recorder()
    task = asyncio.create_task(
        run_pipeline(
            admit(ingest_graph(), effective_settings, {"path": "a.md"}),
            scripted_catalogue(script),
            RESOURCES,
            on_event=recorder,
            cancellation=token,
        )
    )
    await script.started["commit"].wait()
    token.cancel()
    await recorder.wait_for(EventKind.RUN_CANCELLING)
    assert not task.done()
    gate.set()
    result = await task

    assert result.status is RunStatus.CANCELLED
    assert _statuses(result)["commit"] is NodeStatus.SUCCEEDED
    assert result.completed_effects == ("committed:None",)
    cancelling = recorder.index(EventKind.RUN_CANCELLING)
    assert cancelling < recorder.index(EventKind.EFFECT_COMMITTED, "commit")
    assert recorder.kinds()[-1] is EventKind.RUN_CANCELLED


async def test_blocking_call_finishes_at_a_safe_boundary(effective_settings: Any) -> None:
    """A thread-bound call keeps the run cancelling until it returns."""
    release = threading.Event()
    script = Script()

    async def blocking(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await asyncio.to_thread(release.wait)
        return NodeOutput(values={"evidence": ["late"]})

    script.on("dense", blocking)
    token = RunCancellation()
    recorder = Recorder()
    task = asyncio.create_task(
        run_pipeline(
            admit(HYBRID, effective_settings, {"query": "q"}),
            scripted_catalogue(script),
            RESOURCES,
            on_event=recorder,
            cancellation=token,
        )
    )
    await script.started["dense"].wait()
    await recorder.wait_for(EventKind.NODE_COMPLETED, "sparse")
    token.cancel()
    await recorder.wait_for(EventKind.RUN_CANCELLING)
    assert not task.done()
    assert EventKind.RUN_CANCELLED not in recorder.kinds()
    release.set()
    result = await task

    assert result.status is RunStatus.CANCELLED
    assert _statuses(result)["dense"] is NodeStatus.SUCCEEDED
    assert _statuses(result)["fuse"] is NodeStatus.CANCELLED
    assert not script.called("fuse")


async def test_adapter_stops_at_its_own_safe_boundary(effective_settings: Any) -> None:
    """An adapter that sees the shared token and stops is reported as cancelled."""
    script = Script()
    token = RunCancellation()

    async def cooperative(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        token.cancel()
        assert ctx.cancellation.cancelled
        ctx.cancellation.raise_if_cancelled()
        return NodeOutput(values={"evidence": []})

    script.on("dense", cooperative)
    result = await run_pipeline(
        admit(HYBRID, effective_settings, {"query": "q"}),
        scripted_catalogue(script),
        RESOURCES,
        cancellation=token,
        limits=RunLimits(max_concurrency=1),
    )
    assert result.status is RunStatus.CANCELLED
    assert _statuses(result)["dense"] is NodeStatus.CANCELLED
    assert result.failed_node is None


def test_raise_if_cancelled_names_the_reason() -> None:
    """The cancellation error carries the requested reason."""
    token = RunCancellation()
    token.raise_if_cancelled()
    token.cancel("server shutdown")
    with pytest.raises(PipelineCancelledError, match="server shutdown"):
        token.raise_if_cancelled()


async def test_plain_flag_cancelled_before_start_runs_nothing(effective_settings: Any) -> None:
    """A host flag set before the run starts cancels every node."""
    flag = CancellationFlag()
    flag.cancel()
    script = Script()
    result = await run_pipeline(
        admit(HYBRID, effective_settings, {"query": "q"}),
        scripted_catalogue(script),
        RESOURCES,
        cancellation=flag,
    )
    assert result.status is RunStatus.CANCELLED
    assert script.calls == []
    assert set(_statuses(result).values()) == {NodeStatus.CANCELLED}


async def test_cancelling_the_run_task_still_finishes_the_commit(effective_settings: Any) -> None:
    """Cancelling the awaiting task waits for an entered commit, then propagates."""
    gate = asyncio.Event()
    script = _committing_script(gate)
    recorder = Recorder()
    finished: list[str] = []

    async def commit(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await gate.wait()
        finished.append("commit")
        return NodeOutput(values={"summary": {}}, effects=("committed:a.md",))

    script.on("commit", commit)
    task = asyncio.create_task(
        run_pipeline(
            admit(ingest_graph(), effective_settings, {"path": "a.md"}),
            scripted_catalogue(script),
            RESOURCES,
            on_event=recorder,
        )
    )
    await script.started["commit"].wait()
    task.cancel()
    await recorder.wait_for(EventKind.RUN_CANCELLING)
    assert finished == []
    gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished == ["commit"]
    assert recorder.kinds()[-1] is EventKind.RUN_CANCELLED


async def test_cancellation_between_units_keeps_earlier_commits(effective_settings: Any) -> None:
    """Units after the request are cancelled; earlier source commits remain."""
    script = _committing_script()
    token = RunCancellation()

    async def discover(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        return NodeOutput(values={"sources": ["a.md", "b.md", "c.md"]})

    async def read(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        if inputs["sources"] == ("b.md",):
            token.cancel()
        return NodeOutput(values={"documents": []})

    script.on("discover", discover)
    script.on("read", read)
    result = await run_pipeline(
        admit(ingest_graph(), effective_settings, {"path": "docs/"}),
        scripted_catalogue(script),
        RESOURCES,
        cancellation=token,
        units=UnitSplit(node="discover", port="sources"),
    )
    assert result.status is RunStatus.CANCELLED
    assert result.completed_effects == ("committed:a.md",)
    assert [(u.unit_id, u.status) for u in result.units] == [
        ("a.md", NodeStatus.SUCCEEDED),
        ("b.md", NodeStatus.CANCELLED),
        ("c.md", NodeStatus.CANCELLED),
    ]
