"""Task 4.2: per-unit (directory) execution, per-file outcomes and bounded memory."""

from __future__ import annotations

import gc
import weakref
from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import BaseModel
from tests.unit.test_pipeline_runner_support import Recorder, Script, admit, scripted_catalogue
from tests.unit.test_pipeline_support import ingest_graph

from omrg.core.pipelines import (
    EventKind,
    FatalNodeError,
    NodeContext,
    NodeOutput,
    NodeStatus,
    RunStatus,
    UnitSplit,
    run_pipeline,
)

FILES = ["a.md", "b.md", "c.md"]
SPLIT = UnitSplit(node="discover", port="sources")
RESOURCES = {"store": object(), "embedder": object()}


class Chunks(list):
    """List subclass so a test can hold a weak reference to it."""


def _directory_script(fail_on: str | None = None, fatal: bool = False) -> Script:
    script = Script()

    async def discover(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        return NodeOutput(values={"sources": list(FILES)})

    async def read(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        (source,) = inputs["sources"]
        if source == fail_on:
            error = FatalNodeError if fatal else ValueError
            raise error(f"cannot read {source}")
        return NodeOutput(values={"documents": [f"doc:{source}"]})

    async def commit(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        return NodeOutput(
            values={"summary": {"source": ctx.unit_id}},
            effects=(f"committed:{ctx.unit_id}",),
        )

    script.on("discover", discover)
    script.on("read", read)
    script.on("commit", commit)
    return script


async def _run_directory(script: Script, effective_settings: Any, **kwargs: Any):
    snapshot = admit(ingest_graph(), effective_settings, {"path": "docs/"})
    return await run_pipeline(
        snapshot, scripted_catalogue(script), RESOURCES, units=SPLIT, **kwargs
    )


async def test_each_source_runs_the_graph_once(effective_settings: Any) -> None:
    """Discovery runs once; every later node runs once per source unit."""
    script = _directory_script()
    recorder = Recorder()
    result = await _run_directory(script, effective_settings, on_event=recorder)

    assert result.status is RunStatus.SUCCEEDED
    assert script.calls.count(("discover", None)) == 1
    assert [unit for node, unit in script.calls if node == "commit"] == FILES
    assert script.inputs["read"] == [{"sources": (f,)} for f in FILES]
    assert result.completed_effects == tuple(f"committed:{f}" for f in FILES)
    assert [u.unit_id for u in result.units] == FILES
    assert [u.outputs for u in result.units] == [{"summary": {"source": f}} for f in FILES]
    commit_events = [e for e in recorder.events if e.kind is EventKind.EFFECT_COMMITTED]
    assert [e.unit_id for e in commit_events] == FILES
    # The run service reads data.effect to list committed effects after a restart.
    assert [e.data.get("effect") for e in commit_events] == [f"committed:{f}" for f in FILES]
    started = [e.unit_id for e in recorder.events if e.kind is EventKind.UNIT_STARTED]
    assert started == FILES


async def test_failed_file_keeps_sibling_commits(effective_settings: Any) -> None:
    """A failing source fails its unit only; earlier and later commits remain."""
    script = _directory_script(fail_on="b.md")
    recorder = Recorder()
    result = await _run_directory(script, effective_settings, on_event=recorder)

    assert result.status is RunStatus.FAILED
    assert result.failed_node == "read"
    assert result.completed_effects == ("committed:a.md", "committed:c.md")
    units = {u.unit_id: u for u in result.units}
    assert units["a.md"].status is NodeStatus.SUCCEEDED
    assert units["b.md"].status is NodeStatus.FAILED
    assert units["b.md"].failed_node == "read"
    assert "cannot read b.md" in (units["b.md"].error or "")
    assert units["c.md"].status is NodeStatus.SUCCEEDED
    skipped = [(n.node_id, n.unit_id) for n in result.nodes if n.status is NodeStatus.SKIPPED]
    assert skipped == [("chunk", "b.md"), ("embed", "b.md"), ("commit", "b.md")]
    assert "1 of 3" in (result.error or "")
    failed = [e for e in recorder.events if e.kind is EventKind.UNIT_FAILED]
    assert [e.unit_id for e in failed] == ["b.md"]
    assert recorder.kinds()[-1] is EventKind.RUN_FAILED


async def test_fatal_error_stops_later_units(effective_settings: Any) -> None:
    """A fatal node error stops the run; later sources are not processed."""
    script = _directory_script(fail_on="b.md", fatal=True)
    result = await _run_directory(script, effective_settings)

    assert result.status is RunStatus.FAILED
    assert result.completed_effects == ("committed:a.md",)
    assert [(u.unit_id, u.status) for u in result.units] == [
        ("a.md", NodeStatus.SUCCEEDED),
        ("b.md", NodeStatus.FAILED),
        ("c.md", NodeStatus.SKIPPED),
    ]
    assert ("read", "c.md") not in script.calls


async def test_unit_values_are_released_before_the_next_unit(effective_settings: Any) -> None:
    """Chunks of an earlier source are garbage before the next source is read."""
    script = _directory_script()
    refs: list[weakref.ref[Chunks]] = []
    alive_at_read: list[int] = []

    async def chunk(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        value = Chunks([f"chunk:{ctx.unit_id}"])
        refs.append(weakref.ref(value))
        return NodeOutput(values={"chunks": value})

    original_read = script.behaviours["read"]

    async def read(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        script.inputs.clear()  # drop the test recorder's own references
        gc.collect()
        alive_at_read.append(sum(r() is not None for r in refs))
        return await original_read(ctx, inputs, p)

    script.on("chunk", chunk)
    script.on("read", read)
    result = await _run_directory(script, effective_settings)
    assert result.status is RunStatus.SUCCEEDED
    assert alive_at_read == [0, 0, 0]
    assert len(refs) == 3


async def test_node_events_carry_the_unit(effective_settings: Any) -> None:
    """Per-unit node events name their unit; discovery events do not."""
    recorder = Recorder()
    await _run_directory(_directory_script(), effective_settings, on_event=recorder)
    discover = {e.unit_id for e in recorder.events if e.node_id == "discover"}
    commits = [e.unit_id for e in recorder.events if e.node_id == "commit"]
    assert discover == {None}
    assert set(commits) == set(FILES)
    sequences = [e.sequence for e in recorder.events]
    assert sequences == sorted(sequences)


async def test_unknown_split_port_is_rejected_before_any_node(effective_settings: Any) -> None:
    """A split that names no output port is a host error raised before work starts."""
    script = _directory_script()
    snapshot = admit(ingest_graph(), effective_settings, {"path": "docs/"})
    with pytest.raises(ValueError, match="discover.nothing"):
        await run_pipeline(
            snapshot,
            scripted_catalogue(script),
            RESOURCES,
            units=UnitSplit(node="discover", port="nothing"),
        )
    assert script.calls == []


async def test_non_iterable_unit_list_fails_the_run(effective_settings: Any) -> None:
    """A unit source that does not return a sequence fails clearly."""
    script = _directory_script()

    async def discover(ctx: NodeContext, inputs: Mapping[str, Any], p: BaseModel):
        return NodeOutput(values={"sources": 42})

    script.on("discover", discover)
    result = await _run_directory(script, effective_settings)
    assert result.status is RunStatus.FAILED
    assert "discover.sources" in (result.error or "")
    assert not script.called("read")
