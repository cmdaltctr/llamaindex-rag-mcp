"""Shared helpers for the retrieval graph adapter tests (task 3.2).

No runner exists yet, so these helpers chain the registered adapters by
hand in the order a canonical search graph uses. Every adapter is taken
from a catalogue filled by ``register_retrieval_operations``, so the tests
also exercise the registration path. The test at the end keeps the helper
honest.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from omrs.core.pipelines import CancellationFlag, NodeContext, NodeOutput, OperationCatalogue
from omrs.core.retrieval.graph_adapters import register_retrieval_operations


def build_catalogue() -> OperationCatalogue:
    """Return a catalogue with every retrieval operation registered."""
    catalogue = OperationCatalogue()
    register_retrieval_operations(catalogue)
    return catalogue


def node_context(
    node_id: str,
    settings: Any,
    resources: Mapping[str, Any],
    *,
    collection: str | None = "parity",
    cancellation: Any = None,
) -> NodeContext:
    """Return a node context with explicit settings and resources."""
    return NodeContext(
        run_id="run-test",
        node_id=node_id,
        settings=settings,
        resources=dict(resources),
        cancellation=cancellation or CancellationFlag(),
        collection=collection,
    )


async def run_node(
    catalogue: OperationCatalogue,
    operation_id: str,
    context: NodeContext,
    inputs: Mapping[str, Any],
    **params: Any,
) -> NodeOutput:
    """Validate ``params`` against the descriptor and run the adapter once."""
    entry = catalogue.get(operation_id)
    assert entry is not None, operation_id
    return await entry.adapter(context, inputs, entry.descriptor.parameters(**params))


class RaisingReranker:
    """Reranker resource that fails the test when called."""

    backend_name = "raising"
    last_failure_reason: str | None = None

    def rerank(self, query: str, results: list[dict], top_k: int = 5) -> list[dict]:
        """Fail: this path must not run inference."""
        raise AssertionError("reranker must not be called")


class FakeEmbedder:
    """Embedder resource returning a fixed unit vector."""

    model_name = "fake-embed"

    def get_query_embedding(self, query: str) -> list[float]:
        """Return a unit vector so the norm guard stays quiet."""
        return [1.0, 0.0]


async def run_search_chain(
    settings: Any,
    resources: Mapping[str, Any],
    query: str,
    *,
    hybrid: bool,
    prepare: Mapping[str, Any] | None = None,
    rerank_params: Mapping[str, Any] | None = None,
    expand_window: int = 0,
) -> dict[str, NodeOutput]:
    """Chain prepare, dense, (sparse, RRF,) rerank, select and context.

    Args:
        settings: Frozen settings every node receives.
        resources: ``store``, ``embedder`` and ``reranker`` resources.
        query: Query text.
        hybrid: Whether the graph shape fuses dense and sparse branches.
        prepare: Parameters for ``retrieve.prepare_query``.
        rerank_params: Parameters for ``select.rerank``.
        expand_window: Neighbour expansion for ``context.assemble``.

    Returns:
        Every node output keyed by node id.
    """
    catalogue = build_catalogue()
    outputs: dict[str, NodeOutput] = {}

    def ctx(node_id: str) -> NodeContext:
        return node_context(node_id, settings, resources)

    outputs["prepare"] = await run_node(
        catalogue, "retrieve.prepare_query", ctx("prepare"), {"query": query}, **(prepare or {})
    )
    prepared = outputs["prepare"].values["query"]
    outputs["dense"] = await run_node(
        catalogue, "retrieve.dense", ctx("dense"), {"query": prepared}
    )
    evidence = outputs["dense"].values["evidence"]
    if hybrid:
        outputs["sparse"] = await run_node(
            catalogue, "retrieve.sparse", ctx("sparse"), {"query": prepared}
        )
        ranked = (evidence, outputs["sparse"].values["evidence"])
        outputs["fuse"] = await run_node(catalogue, "combine.rrf", ctx("fuse"), {"ranked": ranked})
        evidence = outputs["fuse"].values["evidence"]
    outputs["rerank"] = await run_node(
        catalogue, "select.rerank", ctx("rerank"), {"evidence": evidence}, **(rerank_params or {})
    )
    outputs["select"] = await run_node(
        catalogue,
        "select.threshold",
        ctx("select"),
        {"evidence": outputs["rerank"].values["evidence"]},
    )
    outputs["context"] = await run_node(
        catalogue,
        "context.assemble",
        ctx("context"),
        {"evidence": outputs["select"].values["evidence"]},
        expand_window=expand_window,
    )
    return outputs


def run_chain(*args: Any, **kwargs: Any) -> dict[str, NodeOutput]:
    """Run :func:`run_search_chain` to completion."""
    return asyncio.run(run_search_chain(*args, **kwargs))


def test_catalogue_helper_registers_retrieval_operations() -> None:
    """The helper catalogue holds every retrieval operation."""
    ids = {d.operation_id for d in build_catalogue().descriptors()}
    assert {
        "retrieve.prepare_query",
        "retrieve.dense",
        "retrieve.sparse",
        "combine.rrf",
        "select.rerank",
        "select.threshold",
        "context.assemble",
    } <= ids
