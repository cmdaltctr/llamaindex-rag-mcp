"""Shared helpers for the graph runner tests (tasks 4.1, 4.2 and 4.4).

The helpers register the fixture descriptors from ``test_pipeline_support``
with scripted fake adapters. A test controls completion order with asyncio
events, never with sleeps. The two tests at the end keep the helpers honest.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from pydantic import BaseModel
from tests.unit.test_pipeline_support import fixture_descriptors, fixture_host

from omrg.core.pipelines import (
    AdmissionSnapshot,
    EventKind,
    NodeContext,
    NodeOutput,
    OperationCatalogue,
    OperationDescriptor,
    PipelineEvent,
    ResolverProfileSource,
    admit_pipeline,
    parse_definition,
)
from omrg.core.profiles.resolver import ProfileResolver

WAIT_GUARD_S = 5.0

Behaviour = Callable[[NodeContext, Mapping[str, Any], BaseModel], Awaitable[NodeOutput]]


class Script:
    """Scripted fake adapters keyed by node identifier.

    A node without a behaviour returns ``"<node>.<port>"`` on every output
    port. Every call is recorded with its unit and its inputs.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.inputs: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.contexts: dict[str, list[NodeContext]] = defaultdict(list)
        self.behaviours: dict[str, Behaviour] = {}
        self.started: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self.running = 0
        self.peak = 0
        self.running_ids: set[str] = set()

    def on(self, node_id: str, behaviour: Behaviour) -> None:
        """Script the behaviour of ``node_id``."""
        self.behaviours[node_id] = behaviour

    def adapter_for(self, descriptor: OperationDescriptor) -> Behaviour:
        """Return a recording adapter for ``descriptor``."""

        async def adapter(
            context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
        ) -> NodeOutput:
            self.calls.append((context.node_id, context.unit_id))
            self.inputs[context.node_id].append(dict(inputs))
            self.contexts[context.node_id].append(context)
            self.running += 1
            self.running_ids.add(context.node_id)
            self.peak = max(self.peak, self.running)
            self.started[context.node_id].set()
            try:
                behaviour = self.behaviours.get(context.node_id)
                if behaviour is not None:
                    return await behaviour(context, inputs, params)
                return NodeOutput(
                    values={p.name: f"{context.node_id}.{p.name}" for p in descriptor.outputs}
                )
            finally:
                self.running -= 1
                self.running_ids.discard(context.node_id)

        return adapter

    def called(self, node_id: str) -> bool:
        """Return whether ``node_id`` ran at least once."""
        return any(node == node_id for node, _ in self.calls)


def scripted_catalogue(script: Script) -> OperationCatalogue:
    """Return the fixture catalogue with ``script`` adapters."""
    catalogue = OperationCatalogue()
    for descriptor in fixture_descriptors():
        catalogue.register(descriptor, script.adapter_for(descriptor))
    return catalogue


class Recorder:
    """Async event sink that keeps every event and wakes waiters."""

    def __init__(self) -> None:
        self.events: list[PipelineEvent] = []
        self._waiters: dict[tuple[EventKind, str | None], asyncio.Event] = defaultdict(
            asyncio.Event
        )

    async def __call__(self, event: PipelineEvent) -> None:
        self.events.append(event)
        self._waiters[(event.kind, event.node_id)].set()
        self._waiters[(event.kind, None)].set()

    async def wait_for(self, kind: EventKind, node_id: str | None = None) -> None:
        """Wait until an event of ``kind`` (for ``node_id``) arrives.

        The timeout is a guard so a broken runner fails the test instead of
        hanging it. Ordering never depends on it.
        """
        await asyncio.wait_for(self._waiters[(kind, node_id)].wait(), WAIT_GUARD_S)

    def kinds(self, node_id: str | None = None) -> list[EventKind]:
        """Return event kinds, optionally for one node."""
        return [e.kind for e in self.events if node_id is None or e.node_id == node_id]

    def index(self, kind: EventKind, node_id: str | None = None) -> int:
        """Return the position of the first matching event."""
        return next(
            i
            for i, e in enumerate(self.events)
            if e.kind is kind and (node_id is None or e.node_id == node_id)
        )


class _MetadataStore:
    def __init__(self) -> None:
        self.metadata: dict[str, dict[str, Any]] = {}

    def get_collection_metadata(self, name: str) -> dict[str, Any] | None:
        return dict(self.metadata.get(name, {}))

    def update_collection_metadata(self, name: str, metadata: dict[str, Any]) -> None:
        self.metadata.setdefault(name, {}).update(metadata)


def admit(
    data: dict[str, Any],
    effective_settings: Any,
    inputs: Mapping[str, Any] | None = None,
) -> AdmissionSnapshot:
    """Admit ``data`` against the fixture catalogue and host."""
    resolver = ProfileResolver(
        store=_MetadataStore(),  # type: ignore[arg-type]
        server_profile="documents",
        base=effective_settings(),
        env_overrides={},
    )
    return admit_pipeline(
        parse_definition(data),
        scripted_catalogue(Script()),
        host=fixture_host(),
        profiles=ResolverProfileSource(resolver),
        inputs=dict(inputs or {}),
    )


def edge(source: str, target: str) -> dict[str, Any]:
    """Return an edge from ``"node.port"`` to ``"node.port"``."""
    src_node, src_port = source.split(".")
    dst_node, dst_port = target.split(".")
    return {
        "source": {"node": src_node, "port": src_port},
        "target": {"node": dst_node, "port": dst_port},
    }


def ref(value: str) -> dict[str, str]:
    """Return a port reference for ``"node.port"``."""
    node, port = value.split(".")
    return {"node": node, "port": port}


def query_graph(
    nodes: list[tuple[str, str]],
    edges: list[tuple[str, str]],
    query_targets: list[str],
    outputs: dict[str, str],
) -> dict[str, Any]:
    """Return a query graph with one ``query`` input."""
    return {
        "schema_version": 1,
        "nodes": [{"id": node_id, "operation": op} for node_id, op in nodes],
        "edges": [edge(s, t) for s, t in edges],
        "inputs": [{"name": "query", "kind": "query", "targets": [ref(t) for t in query_targets]}],
        "outputs": [{"name": name, "source": ref(src)} for name, src in outputs.items()],
    }


def test_script_default_output_names_node_and_port() -> None:
    """A node without a behaviour returns ``node.port`` values."""
    script = Script()
    descriptor = next(d for d in fixture_descriptors() if d.operation_id == "combine.rrf")
    adapter = script.adapter_for(descriptor)
    context = NodeContext(
        run_id="r", node_id="fuse", settings=None, resources={}, cancellation=None
    )  # type: ignore[arg-type]
    output = asyncio.run(adapter(context, {"ranked": ()}, None))  # type: ignore[arg-type]
    assert output.values == {"evidence": "fuse.evidence"}
    assert script.calls == [("fuse", None)]


def test_query_graph_admits(effective_settings: Any) -> None:
    """The query-graph helper builds an admissible document."""
    data = query_graph(
        [("dense", "retrieve.dense")], [], ["dense.query"], {"evidence": "dense.evidence"}
    )
    snapshot = admit(data, effective_settings, {"query": "q"})
    assert snapshot.order == ("dense",)
