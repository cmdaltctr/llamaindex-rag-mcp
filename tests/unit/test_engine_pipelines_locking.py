"""The Engine lock covers graphs that write (unify-profiles-and-pipelines, D3, tasks 3.1-3.3).

Read-only graph runs on one Engine overlap. A graph with an enabled
``SOURCE_COMMIT`` step waits for other writing graphs.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict
from tests.unit.test_engine_pipelines_support import (
    FakeStore,
    build_engine,
    chunks,
    retrieval_graph,
)

from omrs.compose_pipelines import EnginePipelines
from omrs.core.pipelines import (
    EffectClass,
    NodeContext,
    NodeOutput,
    OperationCatalogue,
    OperationDescriptor,
    PortKind,
    PortSpec,
    PortType,
    Provenance,
    RunStatus,
)


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _WriteParams(_Params):
    collection: str | None = None


_VALUE = PortType(kind=PortKind.QUERY)
_SUMMARY = PortType(kind=PortKind.COMMIT_SUMMARY, provenance=frozenset({Provenance.COLLECTION}))


class Probe:
    """Fake operations that record how many runs are inside them at once."""

    def __init__(self) -> None:
        self.inside = 0
        self.peak = 0
        self.entered: asyncio.Event | None = None
        self.release: asyncio.Event | None = None
        self.barrier: asyncio.Barrier | None = None

    def adapter(self, port: str) -> Any:
        async def run(
            context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
        ) -> NodeOutput:
            return await self._enter(port)

        return run

    async def _enter(self, port: str) -> NodeOutput:
        self.inside += 1
        self.peak = max(self.peak, self.inside)
        try:
            if port == "summary":
                # Only the writing step can be held open by a test.
                if self.entered is not None:
                    self.entered.set()
                if self.release is not None:
                    await asyncio.wait_for(self.release.wait(), timeout=3)
            elif self.barrier is not None:
                await asyncio.wait_for(self.barrier.wait(), timeout=3)
        finally:
            self.inside -= 1
        return NodeOutput(values={port: {} if port == "summary" else "x"})

    def catalogue(self) -> OperationCatalogue:
        catalogue = OperationCatalogue()
        catalogue.register(
            OperationDescriptor(
                operation_id="probe.read",
                version=1,
                title="Read probe",
                family="probe",
                parameters=_Params,
                outputs=(PortSpec(name="value", type=_VALUE),),
                effect=EffectClass.READ_ONLY,
            ),
            self.adapter("value"),
        )
        catalogue.register(
            OperationDescriptor(
                operation_id="probe.write",
                version=1,
                title="Write probe",
                family="probe",
                parameters=_WriteParams,
                outputs=(PortSpec(name="summary", type=_SUMMARY),),
                effect=EffectClass.SOURCE_COMMIT,
                collection_param="collection",
            ),
            self.adapter("summary"),
        )
        return catalogue


def _graph(operation: str, port: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "nodes": [{"id": "probe", "operation": operation}],
        "edges": [],
        "inputs": [],
        "outputs": [{"name": "out", "source": {"node": "probe", "port": port}}],
    }


def _engine(effective_settings, probe: Probe):
    engine = build_engine(effective_settings())
    engine._pipelines = EnginePipelines(catalogue_factory=probe.catalogue)
    return engine


def test_read_only_runs_on_one_engine_overlap(effective_settings) -> None:
    """Two read-only runs are both inside the step before either ends."""
    probe = Probe()
    engine = _engine(effective_settings, probe)

    async def scenario() -> list:
        probe.barrier = asyncio.Barrier(2)
        graph = _graph("probe.read", "value")
        return await asyncio.gather(
            engine.run_pipeline(graph, inputs={}), engine.run_pipeline(graph, inputs={})
        )

    results = asyncio.run(scenario())
    assert [r.status for r in results] == [RunStatus.SUCCEEDED] * 2, [r.error for r in results]
    assert probe.peak == 2


def test_store_reads_on_one_engine_overlap(effective_settings) -> None:
    """The recorded retrieval graph also runs twice at once on one Engine."""
    store = FakeStore(chunks())
    store.barrier = threading.Barrier(2, timeout=3)
    engine = build_engine(effective_settings(), store)

    async def both() -> list:
        return await asyncio.gather(
            engine.run_pipeline(retrieval_graph(), inputs={"query": "1"}),
            engine.run_pipeline(retrieval_graph(), inputs={"query": "2"}),
        )

    results = asyncio.run(both())
    assert [r.status for r in results] == [RunStatus.SUCCEEDED] * 2, [r.error for r in results]


def test_writing_runs_on_one_engine_never_overlap(effective_settings) -> None:
    """A second graph with an enabled write step waits until the first one ends."""
    probe = Probe()
    engine = _engine(effective_settings, probe)

    async def scenario() -> list:
        probe.entered, probe.release = asyncio.Event(), asyncio.Event()
        graph = _graph("probe.write", "summary")
        first = asyncio.create_task(engine.run_pipeline(graph, inputs={}))
        await asyncio.wait_for(probe.entered.wait(), timeout=3)
        second = asyncio.create_task(engine.run_pipeline(graph, inputs={}))
        await asyncio.sleep(0.1)
        assert probe.inside == 1, "the second writing run started while the first held the lock"
        probe.release.set()
        return await asyncio.gather(first, second)

    results = asyncio.run(scenario())
    assert [r.status for r in results] == [RunStatus.SUCCEEDED] * 2, [r.error for r in results]
    assert probe.peak == 1


def test_a_read_only_run_starts_while_a_writing_run_holds_the_lock(effective_settings) -> None:
    probe = Probe()
    engine = _engine(effective_settings, probe)

    async def scenario() -> tuple:
        probe.entered, probe.release = asyncio.Event(), asyncio.Event()
        writer = asyncio.create_task(
            engine.run_pipeline(_graph("probe.write", "summary"), inputs={})
        )
        await asyncio.wait_for(probe.entered.wait(), timeout=3)
        reader = await asyncio.wait_for(
            engine.run_pipeline(_graph("probe.read", "value"), inputs={}), timeout=3
        )
        assert probe.inside == 1, "only the writing run is inside a step now"
        probe.release.set()
        return reader, await writer

    reader, writer = asyncio.run(scenario())
    assert reader.status is RunStatus.SUCCEEDED, reader.error
    assert writer.status is RunStatus.SUCCEEDED, writer.error


def test_active_runs_returns_to_zero_after_overlapping_runs(effective_settings) -> None:
    probe = Probe()
    engine = _engine(effective_settings, probe)

    async def scenario() -> None:
        probe.barrier = asyncio.Barrier(2)
        graph = _graph("probe.read", "value")
        await asyncio.gather(
            engine.run_pipeline(graph, inputs={}), engine.run_pipeline(graph, inputs={})
        )

    asyncio.run(scenario())
    assert engine._pipelines.active_runs == 0
