"""Standard graphs for a profile duplicate (unify-profiles-and-pipelines, D21).

A duplicate of a built-in profile starts from the canonical ingestion, search
and answer graphs. This module shapes them for one built-in profile. It is
part of the composition root: it names operations of several domains.
"""

from __future__ import annotations

from typing import Any

#: Pipeline slot for each canonical template name.
_SLOT_OF_TEMPLATE = {"ingestion": "ingest", "search": "search", "answer": "answer"}


def profile_templates(engine: Any, base_profile: str) -> dict[str, dict[str, Any]]:
    """Return the Ingest, Search and Answer graphs of a duplicate of ``base_profile``.

    The retrieval chain follows the base profile's own ``retrieval.hybrid_enabled``
    (so ``codebase`` gets its sparse and fusion steps whatever the host default
    is) and the Engine's reranker capability. Each graph names the base profile
    and no collection, and writes no node parameter, so the duplicate behaves
    like the built-in profile, including environment overrides.

    Args:
        engine: The Engine that will validate and run the graphs.
        base_profile: ``documents`` or ``codebase``.

    Returns:
        Graph documents (JSON-compatible dictionaries) by slot: ``ingest``,
        ``search`` and ``answer``.

    Raises:
        ValueError: If the Engine has no profile resolver.
    """
    from .pipeline_templates import canonical_templates

    graph_host = engine._graph_host(None)
    settings = graph_host.profiles.load_profile(base_profile)
    templates = canonical_templates(
        None,
        hybrid=bool(settings.retrieval.hybrid_enabled),
        rerank=graph_host.host.capabilities.get("reranker") is None,
    )
    graphs: dict[str, dict[str, Any]] = {}
    for template in templates:
        graph = template.definition.graph.model_dump(mode="json")
        graph["profile"] = base_profile
        graphs[_SLOT_OF_TEMPLATE[template.name]] = graph
    return graphs
