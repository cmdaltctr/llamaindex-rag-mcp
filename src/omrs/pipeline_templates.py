"""Canonical pipeline graph templates (task 4.5, design D4).

Each template is an editable graph that reproduces one standard Engine
operation with the registered domain operations:

* ``ingestion`` reproduces ``Engine.ingest``. It is the graph that
  :func:`omrs.core.ingestion.graph_adapters.canonical_ingestion_definition`
  returns, so the ingestion index-shaping fingerprint and the template
  share one description.
* ``search`` reproduces ``Engine.search``::

      retrieve.prepare_query -> retrieve.dense [+ retrieve.sparse -> combine.rrf]
      -> select.rerank -> select.threshold -> context.assemble

* ``answer`` reproduces ``Engine.answer``: the search chain, then
  ``answer.prepare_evidence -> answer.synthesise -> answer.cite ->
  verify.claims``.

Graph outputs carry only summaries and results: the commit summary, the
assembled context, or the answer result. No template exposes chunks or
vectors as a graph output.

A template is a starting point. A copy can remove, add or rewire nodes;
validation then checks the edited graph, and the runner follows the saved
connections. This module lives at the composition layer because it names
operations from more than one domain; ``core/pipelines`` stays free of
domain imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core.pipelines import PipelineDefinition

#: Template names, in publication order.
TEMPLATE_NAMES: tuple[str, ...] = ("ingestion", "search", "answer")


@dataclass(frozen=True)
class PipelineTemplate:
    """One published canonical graph.

    Attributes:
        name: Stable template name (``ingestion``, ``search``, ``answer``).
        title: Short display title.
        description: What the template does, in one sentence.
        standard_operation: The Engine method the template reproduces.
        definition: The validated graph document with an empty layout.
    """

    name: str
    title: str
    description: str
    standard_operation: str
    definition: PipelineDefinition


def _edge(source: str, out_port: str, target: str, in_port: str) -> dict[str, Any]:
    return {
        "source": {"node": source, "port": out_port},
        "target": {"node": target, "port": in_port},
    }


def _search_graph(collection: str | None, *, hybrid: bool, rerank: bool) -> dict[str, Any]:
    """Return the search graph document as plain JSON data."""
    nodes: list[dict[str, Any]] = [
        {"id": "prepare", "operation": "retrieve.prepare_query"},
        {"id": "dense", "operation": "retrieve.dense"},
    ]
    edges = [_edge("prepare", "query", "dense", "query")]
    ranked = "dense"
    if hybrid:
        nodes += [
            {"id": "sparse", "operation": "retrieve.sparse"},
            {"id": "fuse", "operation": "combine.rrf"},
        ]
        edges += [
            _edge("prepare", "query", "sparse", "query"),
            _edge("dense", "evidence", "fuse", "ranked"),
            _edge("sparse", "evidence", "fuse", "ranked"),
        ]
        ranked = "fuse"
    nodes += [
        {"id": "rerank", "operation": "select.rerank", "enabled": rerank},
        {"id": "select", "operation": "select.threshold"},
        {"id": "context", "operation": "context.assemble"},
    ]
    edges += [
        _edge(ranked, "evidence", "rerank", "evidence"),
        _edge("rerank", "evidence", "select", "evidence"),
        _edge("select", "evidence", "context", "evidence"),
    ]
    return {
        "schema_version": 1,
        "collection": collection,
        "nodes": nodes,
        "edges": edges,
        "inputs": [
            {
                "name": "query",
                "kind": "query",
                "targets": [{"node": "prepare", "port": "query"}],
            }
        ],
        "outputs": [{"name": "results", "source": {"node": "context", "port": "context"}}],
    }


def _answer_graph(collection: str | None, *, hybrid: bool, rerank: bool) -> dict[str, Any]:
    """Return the answer graph document as plain JSON data."""
    graph = _search_graph(collection, hybrid=hybrid, rerank=rerank)
    graph["nodes"] += [
        {"id": "evidence", "operation": "answer.prepare_evidence"},
        {"id": "synthesise", "operation": "answer.synthesise"},
        {"id": "cite", "operation": "answer.cite"},
        {"id": "verify", "operation": "verify.claims"},
    ]
    graph["edges"] += [
        _edge("context", "context", "evidence", "context"),
        _edge("evidence", "context", "synthesise", "context"),
        _edge("synthesise", "answer", "cite", "answer"),
        _edge("cite", "answer", "verify", "answer"),
    ]
    graph["inputs"][0]["targets"].append({"node": "synthesise", "port": "query"})
    graph["outputs"] = [{"name": "answer", "source": {"node": "verify", "port": "answer"}}]
    return graph


def ingestion_template(collection: str | None = None) -> PipelineDefinition:
    """Return the canonical ingestion graph (same as ``Engine.ingest``).

    Args:
        collection: Target collection. ``None`` uses the host default.

    Returns:
        A definition with one input ``path`` and one output ``summary``.
    """
    from .core.ingestion.graph_adapters import canonical_ingestion_definition

    return canonical_ingestion_definition(collection)


def search_template(
    collection: str | None = None, *, hybrid: bool = False, rerank: bool = True
) -> PipelineDefinition:
    """Return the canonical search graph (same as ``Engine.search``).

    Args:
        collection: Collection to search. ``None`` uses the host default.
        hybrid: Add the sparse branch and RRF fusion, as
            ``retrieval.hybrid_enabled`` does for ``search()``.
        rerank: Enable the rerank node. ``False`` keeps the node but
            bypasses it, for a host without a reranker model.

    Returns:
        A definition with one input ``query`` and one output ``results``.
    """
    from .core.pipelines import parse_definition

    return parse_definition({"graph": _search_graph(collection, hybrid=hybrid, rerank=rerank)})


def answer_template(
    collection: str | None = None, *, hybrid: bool = False, rerank: bool = True
) -> PipelineDefinition:
    """Return the canonical answer graph (same as ``Engine.answer``).

    Args:
        collection: Collection to retrieve from. ``None`` uses the host default.
        hybrid: Add the sparse branch and RRF fusion.
        rerank: Enable the rerank node (see :func:`search_template`).

    Returns:
        A definition with one input ``query`` and one output ``answer``.
    """
    from .core.pipelines import parse_definition

    return parse_definition({"graph": _answer_graph(collection, hybrid=hybrid, rerank=rerank)})


def canonical_templates(
    collection: str | None = None, *, hybrid: bool = False, rerank: bool = True
) -> tuple[PipelineTemplate, ...]:
    """Return the three canonical templates, in :data:`TEMPLATE_NAMES` order.

    Args:
        collection: Collection every template names. ``None`` uses the
            host default.
        hybrid: Shape of the retrieval chain in ``search`` and ``answer``.
        rerank: Whether the rerank node starts enabled.
    """
    return (
        PipelineTemplate(
            name="ingestion",
            title="Ingest sources",
            description="Discover, read, prepare, embed and commit each source.",
            standard_operation="Engine.ingest",
            definition=ingestion_template(collection),
        ),
        PipelineTemplate(
            name="search",
            title="Search",
            description="Retrieve, select and assemble context for a query.",
            standard_operation="Engine.search",
            definition=search_template(collection, hybrid=hybrid, rerank=rerank),
        ),
        PipelineTemplate(
            name="answer",
            title="Answer",
            description="Search, then write, cite and optionally verify an answer.",
            standard_operation="Engine.answer",
            definition=answer_template(collection, hybrid=hybrid, rerank=rerank),
        ),
    )
