"""Task 4.2: adapter contract at run time (context, outputs, progress, catalogue)."""

from __future__ import annotations

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
from tests.unit.test_pipeline_support import fixture_descriptors

from omrg.core.pipelines import (
    EventKind,
    NodeContext,
    NodeOutput,
    OperationCatalogue,
    RunStatus,
    run_pipeline,
)

HYBRID = query_graph(
    [("dense", "retrieve.dense"), ("sparse", "retrieve.sparse"), ("fuse", "combine.rrf")],
    [("dense.evidence", "fuse.ranked"), ("sparse.evidence", "fuse.ranked")],
    ["dense.query", "sparse.query"],
    {"evidence": "fuse.evidence"},
)
RESOURCES = {"store": object(), "embedder": object(), "reranker": object()}


async def _run(snapshot: Any, script: Script, **kwargs: Any):
    return await run_pipeline(snapshot, scripted_catalogue(script), RESOURCES, **kwargs)


async def test_progress_events_belong_to_their_node(effective_settings: Any) -> None:
    """Adapter progress becomes ordered node events with safe data."""
    script = Script()

    async def progressing(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        ctx.progress("searched shard", {"shard": 1})
        return NodeOutput(values={"evidence": []}, summary={"hits": 0})

    script.on("dense", progressing)
    recorder = Recorder()
    await _run(admit(HYBRID, effective_settings, {"query": "q"}), script, on_event=recorder)
    kinds = recorder.kinds("dense")
    assert kinds == [
        EventKind.NODE_QUEUED,
        EventKind.NODE_STARTED,
        EventKind.NODE_PROGRESS,
        EventKind.NODE_COMPLETED,
    ]
    progress = recorder.events[recorder.index(EventKind.NODE_PROGRESS, "dense")]
    assert progress.data == {"shard": 1}
    done = recorder.events[recorder.index(EventKind.NODE_COMPLETED, "dense")]
    assert done.data == {"hits": 0}


async def test_missing_consumed_output_fails_the_producer(effective_settings: Any) -> None:
    """A producer that omits a connected output port fails with the port name."""
    script = Script()

    async def silent(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        return NodeOutput(values={})

    script.on("dense", silent)
    result = await _run(admit(HYBRID, effective_settings, {"query": "q"}), script)
    assert result.failed_node == "dense"
    assert "evidence" in (result.error or "")
    assert "fuse" in result.skipped_nodes


async def test_missing_adapter_fails_before_any_node_runs(effective_settings: Any) -> None:
    """A catalogue without an admitted operation fails the run with no node calls."""
    script = Script()
    catalogue = OperationCatalogue()
    for descriptor in fixture_descriptors():
        if descriptor.operation_id != "combine.rrf":
            catalogue.register(descriptor, script.adapter_for(descriptor))
    recorder = Recorder()
    snapshot = admit(HYBRID, effective_settings, {"query": "q"})
    result = await run_pipeline(snapshot, catalogue, RESOURCES, on_event=recorder)
    assert result.status is RunStatus.FAILED
    assert "combine.rrf" in (result.error or "")
    assert script.calls == []
    assert recorder.kinds() == [EventKind.RUN_FAILED]


async def test_adapters_receive_explicit_settings_resources_and_params(
    effective_settings: Any,
) -> None:
    """The node context carries the admitted settings and read-only resources."""
    data = query_graph(
        [("dense", "retrieve.dense")], [], ["dense.query"], {"evidence": "dense.evidence"}
    )
    data["nodes"][0]["params"] = {"top_k": 3}
    snapshot = admit(data, effective_settings, {"query": "q"})
    script = Script()
    await _run(snapshot, script, run_id="run-1")
    context = script.contexts["dense"][0]
    assert context.run_id == "run-1"
    assert context.settings == snapshot.node("dense").settings
    assert context.controls["retrieval.top_k"] == 3
    assert context.resource("store") is RESOURCES["store"]
    with pytest.raises(TypeError):
        context.resources["store"] = None  # type: ignore[index]
    assert script.inputs["dense"] == [{"query": "q"}]
