"""Index-shaping fingerprint of ingestion graphs (task 3.5, design D5).

The fingerprint hashes operation ids, versions, validated parameters and
upstream connections in the commit node's ancestor slice. Node ids, layout,
titles, the destination collection and query-only branches do not count.
The canonical graph has the standard shape, so its index identity equals
the identity ``ingest_path_async`` writes.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict
from tests.unit.test_ingestion_graph_adapters_support import (
    admit,
    build_catalogue,
    canonical_graph,
    offline_settings,
)

from omrg.core.ingestion.graph_adapters import CHUNK, canonical_ingestion_definition
from omrg.core.ingestion.graph_fingerprint import (
    SHAPE_SCHEMA,
    graph_shape,
    ingestion_shape,
    standard_shape,
)
from omrg.core.pipelines import (
    EffectClass,
    NodeOutput,
    OperationDescriptor,
    PortKind,
    PortSpec,
    PortType,
    parse_definition,
)


def _shape(data: dict[str, Any], catalogue: Any = None) -> Any:
    return graph_shape(parse_definition(data).graph, catalogue or build_catalogue())


def _rename(data: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    renamed = copy.deepcopy(data)
    graph = renamed["graph"]
    for node in graph["nodes"]:
        node["id"] = mapping.get(node["id"], node["id"])
    for edge in graph["edges"]:
        for end in ("source", "target"):
            edge[end]["node"] = mapping.get(edge[end]["node"], edge[end]["node"])
    for graph_input in graph["inputs"]:
        for target in graph_input["targets"]:
            target["node"] = mapping.get(target["node"], target["node"])
    for output in graph["outputs"]:
        output["source"]["node"] = mapping.get(output["source"]["node"], output["source"]["node"])
    return renamed


def _bypass_normalise(data: dict[str, Any]) -> dict[str, Any]:
    changed = copy.deepcopy(data)
    graph = changed["graph"]
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] != "normalise"]
    graph["edges"] = [
        e for e in graph["edges"] if "normalise" not in (e["source"]["node"], e["target"]["node"])
    ] + [
        {
            "source": {"node": "read", "port": "documents"},
            "target": {"node": "enrich", "port": "documents"},
        }
    ]
    return changed


class _NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def _noop(context: Any, inputs: Any, params: Any) -> NodeOutput:
    return NodeOutput(values={})


def _with_query_branch(data: dict[str, Any]) -> dict[str, Any]:
    changed = copy.deepcopy(data)
    graph = changed["graph"]
    graph["nodes"].append({"id": "search", "operation": "retrieve.probe", "params": {}})
    graph["inputs"].append(
        {"name": "query", "kind": "query", "targets": [{"node": "search", "port": "query"}]}
    )
    graph["outputs"].append({"name": "hits", "source": {"node": "search", "port": "evidence"}})
    return changed


def _catalogue_with_extras() -> Any:
    catalogue = build_catalogue()
    catalogue.register(
        OperationDescriptor(
            operation_id="retrieve.probe",
            version=1,
            title="Probe",
            family="retrieve",
            parameters=_NoParams,
            inputs=(PortSpec("query", PortType(PortKind.QUERY)),),
            outputs=(PortSpec("evidence", PortType(PortKind.RANKED_EVIDENCE)),),
            effect=EffectClass.READ_ONLY,
        ),
        _noop,
    )
    catalogue.register(CHUNK.model_copy(update={"version": 2}), _noop)
    return catalogue


# ── Pure fingerprint ────────────────────────────────────────────────────


def test_canonical_graph_has_the_standard_shape() -> None:
    """The canonical template adds nothing to the standard identity."""
    shape = _shape(canonical_graph("documents"))
    assert shape == standard_shape()
    assert shape.standard
    assert shape.identity_block() is None


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(
            lambda d: {
                **d,
                "layout": {
                    "title": "Moved",
                    "positions": {"read": {"x": 9, "y": 4}},
                    "viewport": {"x": 3, "y": 1, "zoom": 2.0},
                },
            },
            id="layout",
        ),
        pytest.param(
            lambda d: _rename(d, {"read": "reader_1", "chunk": "splitter", "commit": "write"}),
            id="node-ids",
        ),
        pytest.param(lambda d: canonical_graph("another_collection"), id="destination"),
        pytest.param(_with_query_branch, id="query-only-branch"),
        pytest.param(
            lambda d: canonical_graph("documents", chunk={"chunk_size": None}),
            id="explicit-inherit",
        ),
    ],
)
def test_presentation_and_query_changes_keep_the_shape(change: Any) -> None:
    """Layout, ids, destination and query-only stages are not index shaping."""
    catalogue = _catalogue_with_extras()
    base = canonical_graph("documents")
    assert _shape(change(base), catalogue) == _shape(base, catalogue)


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(
            lambda d: canonical_graph("documents", chunk={"chunk_size": 256}), id="parameter"
        ),
        pytest.param(
            lambda d: canonical_graph("documents", enrich={"taxonomy_mode": "file_type"}),
            id="enrich-parameter",
        ),
        pytest.param(
            lambda d: canonical_graph("documents", read={"pdf_reader": "pdf_inspector"}),
            id="pdf-reader",
        ),
        pytest.param(_bypass_normalise, id="connection"),
        pytest.param(
            lambda d: (
                _rename(d, {})
                | {
                    "graph": {
                        **d["graph"],
                        "nodes": [
                            {**n, "enabled": False} if n["id"] == "enrich" else n
                            for n in d["graph"]["nodes"]
                        ],
                    }
                }
            ),
            id="disabled-node",
        ),
        pytest.param(
            lambda d: (
                d
                | {
                    "graph": {
                        **d["graph"],
                        "nodes": [
                            {**n, "version": 1} if n["id"] == "chunk" else n
                            for n in d["graph"]["nodes"]
                        ],
                    }
                }
            ),
            id="operation-version",
        ),
    ],
)
def test_shaping_changes_change_the_shape(change: Any) -> None:
    """Operation, version, parameter and connection changes are shaping.

    The extra catalogue registers ``prepare.chunk`` version 2, so the base
    graph resolves to version 2 and the version case pins version 1.
    """
    catalogue = _catalogue_with_extras()
    base = canonical_graph("documents")
    changed = _shape(change(base), catalogue)
    assert changed.fingerprint != _shape(base, catalogue).fingerprint


@pytest.mark.parametrize(
    "changes", [{"chunk": {"chunk_size": 256}}, {"enrich": {"taxonomy_mode": "file_type"}}]
)
def test_non_standard_shape_adds_a_versioned_identity_block(changes: dict) -> None:
    """Only a non-standard shape adds the ``graph_shape`` block."""
    shape = _shape(canonical_graph("documents", **changes))
    assert not shape.standard
    assert shape.identity_block() == {"schema": SHAPE_SCHEMA, "fingerprint": shape.fingerprint}


def test_newer_operation_version_is_not_the_standard_shape() -> None:
    """An unpinned node that resolves to a newer version reprocesses sources."""
    assert not _shape(canonical_graph("documents"), _catalogue_with_extras()).standard


def test_pinned_latest_version_equals_an_unpinned_node() -> None:
    """Admission records the resolved version; pinning it changes nothing."""
    data = canonical_graph("documents")
    pinned = copy.deepcopy(data)
    for node in pinned["graph"]["nodes"]:
        node["version"] = 1
    assert _shape(pinned) == _shape(data)


def test_two_commit_destinations_are_refused() -> None:
    """The first release permits one source-commit destination per recipe."""
    data = canonical_graph("documents")
    data["graph"]["nodes"].append(
        {"id": "commit2", "operation": "commit.source", "params": {"collection": "other"}}
    )
    data["graph"]["edges"].append(
        {
            "source": {"node": "embed", "port": "chunks"},
            "target": {"node": "commit2", "port": "chunks"},
        }
    )
    with pytest.raises(ValueError, match="one source-commit"):
        _shape(data)


def test_admitted_shape_matches_the_saved_graph_shape(
    tmp_path: Any, effective_settings: Any
) -> None:
    """The run shape uses the admitted graph and its resolved versions."""
    catalogue = build_catalogue()
    data = canonical_graph("documents", chunk={"chunk_size": 300})
    snapshot = admit(data, offline_settings(effective_settings), tmp_path, catalogue)
    assert ingestion_shape(snapshot, catalogue) == _shape(data, catalogue)


def test_canonical_definition_has_a_separate_empty_layout() -> None:
    """The template carries execution semantics only."""
    definition = canonical_ingestion_definition(collection="x")
    assert definition.graph.collection == "x"
    assert definition.layout.positions == {}


# ── Step reader (add-pdf-reader-step-setting, task 3.1) ──────────────────


def test_shape_carries_the_reader_of_the_read_node_in_the_commit_slice() -> None:
    """The reader of the node that feeds the commit is part of the shape."""
    shape = _shape(canonical_graph("documents", read={"pdf_reader": "pdf_inspector"}))
    assert shape.pdf_reader == "pdf_inspector"


def test_shape_reader_is_none_when_the_read_node_inherits() -> None:
    """``null`` inherits, so the shape names no reader."""
    assert _shape(canonical_graph("documents")).pdf_reader is None
    assert standard_shape().pdf_reader is None


def test_read_node_outside_the_commit_slice_does_not_set_the_reader() -> None:
    """A second read node that feeds nothing toward the commit is ignored."""
    data = canonical_graph("documents")
    data["graph"]["nodes"].append(
        {"id": "stray", "operation": "read.document", "params": {"pdf_reader": "liteparse"}}
    )
    data["graph"]["edges"].append(
        {
            "source": {"node": "discover", "port": "sources"},
            "target": {"node": "stray", "port": "sources"},
        }
    )
    assert _shape(data).pdf_reader is None


def test_reader_choice_does_not_depend_on_the_node_id() -> None:
    """Renaming the read node keeps the reader and the fingerprint."""
    data = canonical_graph("documents", read={"pdf_reader": "liteparse"})
    renamed = _rename(data, {"read": "reader_1"})
    assert _shape(renamed) == _shape(data)
    assert _shape(renamed).pdf_reader == "liteparse"
