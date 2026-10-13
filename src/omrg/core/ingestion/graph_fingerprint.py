"""Index-shaping fingerprint of an ingestion graph (task 3.5, design D5).

The fingerprint covers the ancestor slice of the graph's one source-commit
node. Each index-shaping node contributes its operation id, version,
enabled state, validated parameters (the collection parameter excluded)
and the hashes of the outputs it reads, in input-port order. A node that
is not index shaping (discovery, identity, commit) is transparent: it
forwards the hashes of its own inputs. Node ids, layout, titles, the
destination collection and query-only branches never contribute.

One shared description gives the standard identity: the canonical
ingestion graph has the *standard shape*. A source identity built with the
standard shape is the existing schema-6 digest, so ``ingest_path_async``
and the canonical graph write the same ``source_index_identity`` and no
existing collection reprocesses. Any other shape adds a versioned
``graph_shape`` block to the identity, so its sources reprocess once on
the next explicit ingest.

The host computes the shape once per admitted run with
:func:`ingestion_shape` and passes it to the adapters as the resource
``ingestion_shape``. Computing a shape never touches the store.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from typing import Any

from ..pipelines import (
    AdmissionSnapshot,
    EffectClass,
    GraphDocument,
    OperationCatalogue,
    OperationDescriptor,
)
from .graph_adapters_catalogue import INGESTION_DESCRIPTORS, canonical_ingestion_definition

#: Version of the ``graph_shape`` identity block and of this algorithm.
SHAPE_SCHEMA = 1

#: Resource name under which the host passes the run's :class:`IngestionShape`.
INGESTION_SHAPE_RESOURCE = "ingestion_shape"

_Lookup = Callable[[str, int | None], OperationDescriptor | None]


@dataclass(frozen=True)
class IngestionShape:
    """The index-shaping fingerprint of one ingestion graph.

    Attributes:
        fingerprint: SHA-256 of the commit node's ancestor slice.
        standard: Whether the shape equals the canonical graph's shape.
    """

    fingerprint: str
    standard: bool

    def identity_block(self) -> dict[str, Any] | None:
        """Return the ``graph_shape`` identity block, or ``None`` when standard."""
        if self.standard:
            return None
        return {"schema": SHAPE_SCHEMA, "fingerprint": self.fingerprint}


def _digest(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Slice:
    """Merkle hashing over the commit node's ancestors."""

    def __init__(
        self, graph: GraphDocument, lookup: _Lookup, versions: Mapping[str, int | None]
    ) -> None:
        self.graph = graph
        self.nodes = {node.id: node for node in graph.nodes}
        self.descriptors: dict[str, OperationDescriptor] = {}
        for node in graph.nodes:
            descriptor = lookup(node.operation, versions.get(node.id, node.version))
            if descriptor is None:
                raise ValueError(
                    f"Operation {node.operation!r} (node {node.id!r}) is not registered. "
                    "Register it before computing the ingestion shape."
                )
            self.descriptors[node.id] = descriptor
        self.feeds: dict[tuple[str, str], list[dict[str, Any] | tuple[str, str]]] = {}
        for edge in graph.edges:
            key = (edge.target.node, edge.target.port)
            self.feeds.setdefault(key, []).append((edge.source.node, edge.source.port))
        for graph_input in graph.inputs:
            for target in graph_input.targets:
                key = (target.node, target.port)
                self.feeds.setdefault(key, []).append({"input": graph_input.kind.value})
        self._memo: dict[str, str] = {}

    def commit_nodes(self) -> list[str]:
        return [
            node.id
            for node in self.graph.nodes
            if node.enabled and self.descriptors[node.id].effect is EffectClass.SOURCE_COMMIT
        ]

    def _inputs(self, node_id: str) -> list[Any]:
        ports = []
        for port in self.descriptors[node_id].inputs:
            refs: list[Any] = []
            for feed in self.feeds.get((node_id, port.name), []):
                refs.extend(self._output(feed))
            ports.append([port.name, refs])
        return ports

    def _output(self, feed: dict[str, Any] | tuple[str, str]) -> list[Any]:
        if isinstance(feed, dict):
            return [feed]
        node_id, port = feed
        if not self.descriptors[node_id].index_shaping:
            return [ref for _name, refs in self._inputs(node_id) for ref in refs]
        return [{"node": self.node_hash(node_id), "port": port}]

    def node_hash(self, node_id: str) -> str:
        if node_id not in self._memo:
            node = self.nodes[node_id]
            descriptor = self.descriptors[node_id]
            params = descriptor.parameters.model_validate(node.params).model_dump(mode="json")
            params.pop(descriptor.collection_param or "", None)
            self._memo[node_id] = _digest(
                {
                    "operation": descriptor.operation_id,
                    "version": descriptor.version,
                    "enabled": node.enabled,
                    "params": params,
                    "inputs": self._inputs(node_id),
                }
            )
        return self._memo[node_id]

    def fingerprint(self) -> str:
        commits = self.commit_nodes()
        if len(commits) > 1:
            raise ValueError(
                "An ingestion graph permits one source-commit destination; found "
                f"{len(commits)} ({', '.join(commits)}). Keep one commit node."
            )
        if commits:
            body: Any = {"commit": [refs for _name, refs in self._inputs(commits[0])]}
        else:
            body = {
                "shaping": sorted(
                    self.node_hash(n.id)
                    for n in self.graph.nodes
                    if self.descriptors[n.id].index_shaping
                )
            }
        return _digest({"schema": SHAPE_SCHEMA, **body})


def _catalogue_lookup(catalogue: OperationCatalogue) -> _Lookup:
    def lookup(operation: str, version: int | None) -> OperationDescriptor | None:
        entry = catalogue.get(operation, version)
        return entry.descriptor if entry is not None else None

    return lookup


def _own_lookup(operation: str, version: int | None) -> OperationDescriptor | None:
    matches = [d for d in INGESTION_DESCRIPTORS if d.operation_id == operation]
    if version is not None:
        matches = [d for d in matches if d.version == version]
    return max(matches, key=lambda d: d.version) if matches else None


@cache
def _standard_fingerprint() -> str:
    graph = canonical_ingestion_definition().graph
    return _Slice(graph, _own_lookup, {}).fingerprint()


def standard_shape() -> IngestionShape:
    """Return the shape of the canonical graph (standard ingestion)."""
    return IngestionShape(_standard_fingerprint(), standard=True)


def _shape(
    graph: GraphDocument, lookup: _Lookup, versions: Mapping[str, int | None]
) -> IngestionShape:
    fingerprint = _Slice(graph, lookup, versions).fingerprint()
    return IngestionShape(fingerprint, standard=fingerprint == _standard_fingerprint())


def graph_shape(graph: GraphDocument, catalogue: OperationCatalogue) -> IngestionShape:
    """Return the shape of a saved graph; unpinned nodes use the latest version.

    Raises:
        ValueError: If an operation is unknown or the graph has more than one
            enabled source-commit node.
    """
    return _shape(graph, _catalogue_lookup(catalogue), {})


def ingestion_shape(snapshot: AdmissionSnapshot, catalogue: OperationCatalogue) -> IngestionShape:
    """Return the shape of an admitted run, with its resolved versions.

    Raises:
        ValueError: As :func:`graph_shape`.
    """
    versions = {node.node_id: node.version for node in snapshot.nodes}
    return _shape(snapshot.graph, _catalogue_lookup(catalogue), versions)
