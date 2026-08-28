"""Lazy adapter for the optional Leiden community-detection backend.

Wraps ``leidenalg`` + ``igraph`` (the ``community-leiden`` extra).  This
module is an acyclic integration leaf: it imports neither ``core/`` nor
any other project module, and the heavy imports happen inside the
functions so importing this adapter never pulls igraph into a base
installation (AGENTS.md invariant: optional extras must not change the
base import surface).

The NetworkX-to-igraph conversion preserves:
- stable node identifiers (index map, membership mapped back to originals),
- isolated nodes (every graph node becomes an igraph vertex),
- edge weights (``weight`` attribute, default 1.0, forwarded to the
  partition call),
- resolution semantics (RBConfigurationVertexPartition at γ=1.0, matching
  Louvain's default resolution),
- the injected seed (``find_partition(seed=...)`` drives the optimiser's
  RNG, giving deterministic partitions).

Note: RBConfigurationVertexPartition's quality function is defined for
positive edge weights; document-graph similarity edges are thresholded
above zero before they reach the graph, and code-graph edges are
unweighted (1.0).
"""

from __future__ import annotations

from collections.abc import Hashable

import networkx as nx

_INSTALL_HINT = (
    "COMMUNITY_ALGORITHM=leiden requires the optional community-leiden "
    "extra. Install it with: uv sync --extra community-leiden "
    "(or: pip install 'rag-mcp[community-leiden]'). Leiden does not fall "
    "back to Louvain — an explicit algorithm selection is an operator "
    "contract."
)


def is_leiden_available() -> bool:
    """Return ``True`` when leidenalg and igraph are importable.

    Probes both imports without holding references, so a ``False`` result
    costs two failed imports and nothing else.
    """
    try:
        import igraph  # noqa: F401
        import leidenalg  # noqa: F401
    except ImportError:
        return False
    return True


def require_leiden_installed() -> None:
    """Raise ``ImportError`` with the installation instruction when missing.

    Registered as the Leiden strategy's availability probe so the
    composition root fails startup with an actionable message instead of
    silently falling back to Louvain (design decision 4).
    """
    if not is_leiden_available():
        raise ImportError(_INSTALL_HINT)


def leiden_partition(
    graph: nx.Graph,
    *,
    seed: int = 0,
    resolution: float = 1.0,
) -> list[set[Hashable]]:
    """Partition *graph* into communities using flat Leiden.

    Args:
        graph: Undirected NetworkX graph.  Node identifiers may be any
            hashable; they are mapped to stable igraph indices and the
            returned sets contain the original identifiers.
        seed: Seed forwarded to ``leidenalg.find_partition`` for
            deterministic output.
        resolution: RBConfigurationVertexPartition resolution parameter γ.
            Default 1.0 matches Louvain's default resolution; higher γ
            yields more, smaller communities.

    Returns:
        Flat partition as a list of node sets, one per detected community.

    Raises:
        ImportError: When the community-leiden extra is not installed.
    """
    import igraph as ig
    import leidenalg

    # Stable identifier mapping: iteration order of graph.nodes() fixes the
    # vertex indices, so the same graph always converts identically.
    nodes = list(graph.nodes())
    index = {node: i for i, node in enumerate(nodes)}
    # Edges and weights must stay index-aligned, so build both in one pass
    # over graph.edges() rather than two comprehensions that could drift.
    edges: list[tuple[int, int]] = []
    weights: list[float] = []
    for u, v in graph.edges():
        edges.append((index[u], index[v]))
        weights.append(float(graph[u][v].get("weight", 1.0)))

    ig_graph = ig.Graph(n=len(nodes), edges=edges, directed=False)

    partition_object = leidenalg.find_partition(
        ig_graph,
        leidenalg.RBConfigurationVertexPartition,
        weights=weights if edges else None,
        resolution_parameter=resolution,
        seed=seed,
    )

    # Map memberships back to the original node identifiers; isolated
    # nodes are vertices with no edges and appear as singleton
    # communities via the membership array.
    communities: dict[int, set[Hashable]] = {}
    for vertex_idx, community_idx in enumerate(partition_object.membership):
        communities.setdefault(community_idx, set()).add(nodes[vertex_idx])
    return list(communities.values())
