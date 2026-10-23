"""Shared community-detection strategies for codebase and document graphs.

Owns the flat partition contract, the lazy strategy registry, and the
partition validation shared by both graph consumers (design decision 1).
Consumers keep their domain-specific formatting — this boundary returns
only flat node sets, and no algorithm-specific object (igraph, leidenalg)
escapes it (design decision 5).

This package never imports a concrete strategy module at module level;
strategies resolve through :mod:`core.community.registry` on demand.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from typing import Any

import networkx as nx

from .registry import available, get, register, verify_available

# A flat partition: each element is one community's node set.
Partition = list[set[Hashable]]
# Strategy contract: ``partition(graph, *, seed) -> Partition``.
CommunityStrategy = Callable[..., Partition]

__all__ = [
    "Partition",
    "CommunityStrategy",
    "available",
    "get",
    "partition_graph",
    "register",
    "validate_partition",
    "verify_available",
]


def validate_partition(partition: Any, nodes: Iterable[Hashable]) -> None:
    """Validate the flat partition contract.

    A valid partition covers every input node exactly once: communities are
    non-empty, pairwise disjoint, and their union equals the input node set.

    Args:
        partition: Candidate partition from a strategy.
        nodes: The graph's nodes (any iterable).

    Raises:
        ValueError: When the partition is not a list of sets, contains an
            empty community, repeats a node, or misses input nodes.
    """
    if not isinstance(partition, list) or not all(isinstance(c, set) for c in partition):
        raise ValueError(
            "Community strategy must return list[set[Hashable]]; "
            f"got {type(partition).__name__} with elements "
            f"{[type(c).__name__ for c in partition] if isinstance(partition, list) else 'n/a'}. "
            "Algorithm-specific result objects must not escape the strategy boundary."
        )

    seen: set[Hashable] = set()
    for community in partition:
        if not community:
            raise ValueError("Community strategy returned an empty community.")
        overlap = seen & community
        if overlap:
            raise ValueError(
                f"Node(s) {sorted(map(str, overlap))[:5]} appear in more than "
                "one community; the partition contract requires disjoint "
                "communities."
            )
        seen |= community

    # Materialise once: the docstring accepts any iterable, and a one-shot
    # iterable consumed by ``missing`` would make the count below lie.
    node_set = set(nodes)
    missing = node_set - seen
    if missing:
        raise ValueError(
            f"Partition covers {len(seen)} nodes but the graph has "
            f"{len(node_set)} node(s); missing: {sorted(map(str, missing))[:5]}. "
            "The partition contract requires complete coverage."
        )


def partition_graph(
    graph: nx.Graph,
    *,
    algorithm: str,
    seed: int,
) -> Partition:
    """Resolve *algorithm* through the registry and partition *graph*.

    Single dispatch point shared by both graph consumers.  The returned
    partition is validated against the flat contract before it leaves the
    strategy boundary.

    Args:
        graph: Undirected graph.  Callers convert directed graphs and handle
            small-graph bypasses before dispatch.
        algorithm: Registered strategy name (e.g. ``"louvain"``, ``"leiden"``).
        seed: Operator-configured seed forwarded to the strategy.

    Returns:
        Validated flat partition.

    Raises:
        KeyError: If *algorithm* is not registered (lists available names).
        ImportError: If the strategy or its optional dependency is missing.
        ValueError: If the strategy violates the partition contract.
    """
    strategy = get(algorithm)
    result = strategy(graph, seed=seed)
    validate_partition(result, graph.nodes())
    return result
