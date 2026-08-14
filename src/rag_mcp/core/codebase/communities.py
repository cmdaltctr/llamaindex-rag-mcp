"""Deterministic community, hub, and bridge detection over the code graph.

Split out of ``code_graph.py`` (task 8.4). Detection uses NetworkX graph
algorithms only — there is no LLM involvement anywhere in this module
(AGENTS.md invariant #8), so results are reproducible for a given graph.

Community partitioning dispatches through the shared ``core/community``
registry (design decision 2): this module keeps the small-graph bypass,
the seeded resolution, and the domain formatting (labels, edge counts).
"""

from __future__ import annotations

import logging
from pathlib import Path

import networkx as nx

from ..community import partition_graph
from ..settings import EffectiveSettings, resolve_effective_settings
from .code_graph import Bridge, Community, Hub

logger = logging.getLogger(__name__)


def detect_communities(
    graph: nx.DiGraph,
    settings: EffectiveSettings | None = None,
) -> list[Community]:
    """Detect communities in the code graph via the configured strategy.

    Partitions the graph into clusters of related files using the
    ``community_algorithm`` strategy resolved through the shared registry,
    seeded with ``community_seed``. Each community is labelled with
    representative file names.

    Args:
        graph: The code graph as a ``networkx.DiGraph``.
        settings: Effective settings carrying the algorithm name and seed.
            Defaults to the composition-root instance (``None`` is only
            sanctioned at the entry-point boundary; the codebase-map
            boundary passes its resolved instance explicitly).

    Returns:
        List of ``Community`` objects with labels, files, and edge counts.
    """
    effective = resolve_effective_settings(settings)

    if graph.number_of_nodes() < 5:
        # Small graph: single community.
        files = list(graph.nodes())
        return [
            Community(
                label=", ".join(Path(f).name for f in files[:3]),
                files=files,
                edge_count=graph.number_of_edges(),
            )
        ]

    # Convert to undirected for partitioning.
    undirected = graph.to_undirected()

    try:
        communities_sets = partition_graph(
            undirected,
            algorithm=effective.community_algorithm,
            seed=effective.community_seed,
        )
    except Exception as exc:
        logger.warning("Community detection (%s) failed: %s", effective.community_algorithm, exc)
        return [
            Community(
                label="all",
                files=list(graph.nodes()),
                edge_count=graph.number_of_edges(),
            )
        ]

    communities: list[Community] = []
    for comm_set in communities_sets:
        files = sorted(comm_set)
        # Label by top filenames.
        filenames = [Path(f).stem for f in files[:3]]
        label = "/".join(filenames) if filenames else "unnamed"

        # Count internal edges.
        internal_edges = sum(1 for u, v in graph.edges() if u in comm_set and v in comm_set)

        communities.append(
            Community(
                label=label,
                files=files,
                edge_count=internal_edges,
            )
        )

    # Sort by size (largest first).
    communities.sort(key=lambda c: len(c.files), reverse=True)
    return communities


def detect_hubs(graph: nx.DiGraph) -> list[Hub]:
    """Identify hub nodes — files with high in-degree.

    A hub is any node in the top 10% of in-degree, or any node with
    in-degree ≥ 5, whichever is more inclusive.

    Args:
        graph: The code graph as a ``networkx.DiGraph``.

    Returns:
        List of ``Hub`` objects sorted by in-degree (descending).
    """
    if graph.number_of_nodes() == 0:
        return []

    in_degrees = dict(graph.in_degree())
    if not in_degrees:
        return []

    max_degree = max(in_degrees.values())
    if max_degree == 0:
        return []

    # Top 10% threshold.
    sorted_degrees = sorted(in_degrees.values(), reverse=True)
    top_10_percent_idx = max(1, len(sorted_degrees) // 10)
    top_10_threshold = sorted_degrees[top_10_percent_idx - 1]

    # More inclusive of the two criteria.
    threshold = min(top_10_threshold, 5)

    hubs = [
        Hub(file=node, in_degree=degree)
        for node, degree in in_degrees.items()
        if degree >= threshold
    ]
    hubs.sort(key=lambda h: h.in_degree, reverse=True)
    return hubs


def detect_bridges(
    graph: nx.DiGraph,
    communities: list[Community],
) -> list[Bridge]:
    """Identify bridge nodes connecting separate communities.

    Bridge nodes are detected by high betweenness centrality — they lie
    on shortest paths between different communities.

    Args:
        graph: The code graph as a ``networkx.DiGraph``.
        communities: List of detected communities.

    Returns:
        List of ``Bridge`` objects with betweenness scores and community indices.
    """
    if graph.number_of_nodes() < 5 or len(communities) < 2:
        return []

    # Compute betweenness centrality.
    try:
        betweenness = nx.betweenness_centrality(graph.to_undirected())
    except Exception as exc:
        logger.warning("Betweenness centrality computation failed: %s", exc)
        return []

    # Map nodes to community indices.
    node_to_comm: dict[str, int] = {}
    for i, comm in enumerate(communities):
        for node in comm.files:
            node_to_comm[node] = i

    # Find nodes that connect different communities.
    bridges: list[Bridge] = []
    for node, score in betweenness.items():
        if score <= 0:
            continue
        # Check if this node has edges to multiple communities.
        neighbor_comms: set[int] = set()
        for neighbor in graph.neighbors(node):
            comm_idx = node_to_comm.get(neighbor)
            if comm_idx is not None:
                neighbor_comms.add(comm_idx)
        # Also check incoming edges.
        for predecessor in graph.predecessors(node):
            comm_idx = node_to_comm.get(predecessor)
            if comm_idx is not None:
                neighbor_comms.add(comm_idx)

        if len(neighbor_comms) >= 2:
            bridges.append(
                Bridge(
                    file=node,
                    betweenness=score,
                    communities=sorted(neighbor_comms),
                )
            )

    bridges.sort(key=lambda b: b.betweenness, reverse=True)
    return bridges
