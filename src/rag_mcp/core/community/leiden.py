"""Optional Leiden community strategy backed by the community-leiden extra.

Delegates to ``integrations/leidenalg.py`` at call time (design decision 3)
so neither importing this module nor resolving it through the registry
pulls ``leidenalg`` or ``igraph`` into a base installation.  Availability
is checked by the registered probe (``require_leiden_installed``), which
the composition root calls at startup — an explicit ``leiden`` selection
fails with an installation instruction instead of silently falling back
to Louvain.
"""

from __future__ import annotations

from collections.abc import Hashable

import networkx as nx


def partition(graph: nx.Graph, *, seed: int = 0) -> list[set[Hashable]]:
    """Partition *graph* using flat Leiden via the integration adapter.

    Args:
        graph: Undirected graph.  Callers convert directed graphs before
            dispatch.
        seed: Random seed forwarded to the Leiden optimiser.

    Returns:
        Flat partition as a list of node sets, mapped back to the original
        node identifiers.  Validated against the shared partition contract
        by ``core.community.partition_graph`` before reaching consumers.
    """
    from ...integrations.leidenalg import leiden_partition

    return leiden_partition(graph, seed=seed)
