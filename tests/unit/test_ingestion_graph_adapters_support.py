"""Shared helpers for the ingestion graph-adapter tests (tasks 3.4 and 3.5).

The helpers admit an ingestion graph with the real ``admit_pipeline`` and
then chain the registered adapters by hand, one source unit at a time, the
way the runner does with a ``UnitSplit`` on ``discover.sources``. A fake
profile source returns the test settings unchanged, so admission applies
only graph and node overrides. This module holds no tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from llama_index.core import Settings as LlamaIndexSettings

from omrg.core.ingestion.graph_adapters import (
    canonical_ingestion_definition,
    register_ingestion_operations,
)
from omrg.core.ingestion.graph_fingerprint import INGESTION_SHAPE_RESOURCE, ingestion_shape
from omrg.core.pipelines import (
    AdmissionSnapshot,
    CancellationFlag,
    HostContext,
    NodeContext,
    NodeOutput,
    OperationCatalogue,
    admit_pipeline,
)

#: Node ids of the canonical ingestion graph, in order.
CANONICAL_NODES = (
    "discover",
    "identify",
    "read",
    "normalise",
    "enrich",
    "chunk",
    "embed",
    "commit",
)


def offline_settings(effective_settings: Any, **overrides: Any) -> Any:
    """Return the offline settings the parity snapshot was built with."""
    return effective_settings(
        extraction_mode="disabled", pdf_reader="pypdf", ocr_fallback_enabled=False, **overrides
    )


def build_catalogue() -> OperationCatalogue:
    """Return a catalogue that holds only the ingestion families."""
    catalogue = OperationCatalogue()
    register_ingestion_operations(catalogue)
    return catalogue


class FixedProfiles:
    """Profile source that returns one settings object for every collection."""

    def __init__(self, settings: Any) -> None:
        """Keep *settings* for every resolution."""
        self.settings = settings

    def resolve(self, collection: str) -> Any:
        """Return the fixed settings."""
        return self.settings

    def load_profile(self, profile_name: str) -> Any:
        """Return the fixed settings."""
        return self.settings

    def environment_keys(self) -> frozenset[str]:
        """Return no environment keys."""
        return frozenset()


def canonical_graph(collection: str, **changes: Any) -> dict[str, Any]:
    """Return the canonical ingestion definition as JSON-like data.

    Args:
        collection: Collection the graph writes to.
        changes: ``node_id`` to parameter dict, merged into that node.
    """
    data = canonical_ingestion_definition(collection=collection).model_dump(mode="json")
    for node in data["graph"]["nodes"]:
        if node["id"] in changes:
            node["params"] = {**node["params"], **changes[node["id"]]}
    return data


def admit(
    data: Mapping[str, Any],
    settings: Any,
    root: Any,
    catalogue: OperationCatalogue | None = None,
) -> AdmissionSnapshot:
    """Admit *data* with *settings* for the path *root*."""
    return admit_pipeline(
        data,
        catalogue or build_catalogue(),
        host=HostContext(capabilities={"store": None, "embedder": None}),
        profiles=FixedProfiles(settings),
        inputs={"path": str(root)},
    )


def resources(
    snapshot: AdmissionSnapshot, catalogue: OperationCatalogue, store: Any, **extra: Any
) -> dict[str, Any]:
    """Return run resources: store, embedder and the run's ingestion shape."""
    return {
        "store": store,
        "embedder": LlamaIndexSettings.embed_model,
        INGESTION_SHAPE_RESOURCE: ingestion_shape(snapshot, catalogue),
        **extra,
    }


async def invoke(
    snapshot: AdmissionSnapshot,
    catalogue: OperationCatalogue,
    run_resources: Mapping[str, Any],
    node_id: str,
    inputs: Mapping[str, Any],
    *,
    token: Any = None,
    unit_id: str | None = None,
) -> NodeOutput:
    """Invoke one admitted node's adapter as the runner would."""
    node = snapshot.node(node_id)
    entry = catalogue.get(node.operation, node.version)
    assert entry is not None
    params = entry.descriptor.parameters.model_validate(node.params)
    context = NodeContext(
        run_id="hand",
        node_id=node_id,
        settings=node.settings,
        resources=run_resources,
        cancellation=token or CancellationFlag(),
        collection=node.collection,
        unit_id=unit_id,
    )
    return await entry.adapter(context, inputs, params)


def _feeds(snapshot: AdmissionSnapshot) -> dict[tuple[str, str], tuple[str, str]]:
    graph = snapshot.graph
    feeds = {(e.target.node, e.target.port): (e.source.node, e.source.port) for e in graph.edges}
    for graph_input in graph.inputs:
        for target in graph_input.targets:
            feeds[(target.node, target.port)] = ("", graph_input.name)
    return feeds


async def run_by_hand(
    snapshot: AdmissionSnapshot,
    catalogue: OperationCatalogue,
    run_resources: Mapping[str, Any],
    *,
    token: Any = None,
) -> list[NodeOutput]:
    """Run a linear ingestion graph one source unit at a time.

    The first node discovers the units. Every later node runs once per
    unit, with the unit delivered as a one-item tuple, as the runner's
    ``UnitSplit`` does. Disabled nodes forward their bypass input.

    Returns:
        The commit node output of each unit, in discovery order.
    """
    feeds = _feeds(snapshot)
    order = snapshot.order
    values: dict[tuple[str, str], Any] = {("", k): v for k, v in snapshot.inputs.items()}
    first = order[0]
    found = await invoke(
        snapshot, catalogue, run_resources, first, {"sources": values[feeds[(first, "sources")]]}
    )
    outputs = []
    for unit in found.values["sources"]:
        unit_values = {**values, (first, "sources"): (unit,)}
        last: NodeOutput | None = None
        for node_id in order[1:]:
            node = snapshot.node(node_id)
            entry = catalogue.get(node.operation, node.version)
            assert entry is not None
            inputs = {
                port.name: unit_values[feeds[(node_id, port.name)]]
                for port in entry.descriptor.inputs
                if (node_id, port.name) in feeds
            }
            if not node.enabled:
                bypass = entry.descriptor.bypass
                assert bypass is not None
                unit_values[(node_id, bypass.output_port)] = inputs[bypass.input_port]
                continue
            last = await invoke(
                snapshot, catalogue, run_resources, node_id, inputs, token=token, unit_id="u"
            )
            for port, value in last.values.items():
                unit_values[(node_id, port)] = value
        assert last is not None
        outputs.append(last)
    return outputs
