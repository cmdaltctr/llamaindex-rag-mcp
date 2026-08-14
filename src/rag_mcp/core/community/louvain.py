"""Built-in NetworkX Louvain community strategy.

Native strategy: NetworkX is a base dependency, so this module is always
importable.  It registers against the shared flat partition contract in
``core/community`` and accepts the injected seed (default ``0``) so repeated
runs on the same graph return equivalent memberships (design decision 3).
"""

from __future__ import annotations

from collections.abc import Hashable

import networkx as nx


def partition(graph: nx.Graph, *, seed: int = 0) -> list[set[Hashable]]:
    """Partition *graph* into communities using seeded Louvain.

    Args:
        graph: Undirected graph.  Callers convert directed graphs before
            dispatch.
        seed: Random seed for the algorithm's internal randomisation.
            The default ``0`` satisfies the deterministic-graph invariant
            (AGENTS.md #8) when no operator seed is configured.

    Returns:
        Flat partition as a list of node sets.  Each input node appears in
        exactly one non-empty community.
    """
    communities = nx.algorithms.community.louvain_communities(graph, seed=seed)
    return [set(community) for community in communities]
