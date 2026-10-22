"""Task 4.2 (lead decision on D3): a failed unit starts no further source commit."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel
from tests.unit.test_pipeline_runner_support import (
    Recorder,
    Script,
    admit,
    ref,
    scripted_catalogue,
)
from tests.unit.test_pipeline_support import ingest_graph

from omrs.core.pipelines import (
    EventKind,
    NodeContext,
    NodeOutput,
    NodeStatus,
    RunLimits,
    RunStatus,
    run_pipeline,
)

RESOURCES = {"store": object(), "embedder": object()}


def _mixed_graph() -> dict[str, Any]:
    """Ingestion chain plus an independent dense branch in the same unit."""
    data = ingest_graph()
    data["nodes"].insert(0, {"id": "dense", "operation": "retrieve.dense"})
    data["inputs"].append({"name": "query", "kind": "query", "targets": [ref("dense.query")]})
    data["outputs"].append({"name": "evidence", "source": ref("dense.evidence")})
    return data


def _statuses(result: Any) -> dict[str, NodeStatus]:
    return {n.node_id: n.status for n in result.nodes}


async def _broken(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel) -> NodeOutput:
    raise RuntimeError("index offline")


async def _commit(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel) -> NodeOutput:
    return NodeOutput(values={"summary": {}}, effects=("committed:a.md",))


async def test_failed_unit_skips_a_commit_on_an_independent_branch(
    effective_settings: Any,
) -> None:
    """Read-only and model-call siblings finish; the commit does not start."""
    script = Script()
    script.on("dense", _broken)
    script.on("commit", _commit)
    recorder = Recorder()
    result = await run_pipeline(
        admit(_mixed_graph(), effective_settings, {"path": "a.md", "query": "q"}),
        scripted_catalogue(script),
        RESOURCES,
        on_event=recorder,
    )

    assert result.status is RunStatus.FAILED
    assert result.failed_node == "dense"
    statuses = _statuses(result)
    assert statuses["embed"] is NodeStatus.SUCCEEDED
    assert statuses["commit"] is NodeStatus.SKIPPED
    assert not script.called("commit")
    assert result.completed_effects == ()
    skipped = recorder.events[recorder.index(EventKind.NODE_SKIPPED, "commit")]
    assert "dense" in skipped.message
    assert EventKind.NODE_STARTED not in recorder.kinds("commit")


async def test_entered_commit_completes_when_a_sibling_fails(effective_settings: Any) -> None:
    """A commit that started before the failure finishes and is disclosed."""
    script = Script()
    gate = asyncio.Event()

    async def fail_after_commit_starts(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await script.started["commit"].wait()
        raise RuntimeError("index offline")

    async def commit(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        await gate.wait()
        return await _commit(ctx, inputs, p)

    script.on("dense", fail_after_commit_starts)
    script.on("commit", commit)
    recorder = Recorder()
    task = asyncio.create_task(
        run_pipeline(
            admit(_mixed_graph(), effective_settings, {"path": "a.md", "query": "q"}),
            scripted_catalogue(script),
            RESOURCES,
            on_event=recorder,
            limits=RunLimits(exclusive_effects=frozenset()),
        )
    )
    await recorder.wait_for(EventKind.NODE_FAILED, "dense")
    gate.set()
    result = await task

    assert result.status is RunStatus.FAILED
    assert result.failed_node == "dense"
    assert _statuses(result)["commit"] is NodeStatus.SUCCEEDED
    assert result.completed_effects == ("committed:a.md",)
