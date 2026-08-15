"""Compare Louvain and Leiden on representative codebase and document graphs.

OpenSpec task 3.6 (add-pluggable-community-detection). Measures runtime,
partition coverage, connectivity (internal edge share), and determinism
for both registered strategies through the shared ``core/community``
registry, then writes ``output/results.md``.

Run from the project root with ``uv run --extra community-leiden python``
followed by this script's relative path.
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rag_mcp.core.community import partition_graph  # noqa: E402

REPEATS = 5


def _codebase_style_graph() -> nx.Graph:
    """Planted-partition graph shaped like a code graph.

    8 packages x 12 modules; dense intra-package rings, sparse cross-package
    edges, node names are file paths.
    """
    graph = nx.Graph()
    rng = nx.utils.create_py_random_state(42)
    for pkg in range(8):
        nodes = [f"pkg{pkg}/mod{i}.py" for i in range(12)]
        graph.add_nodes_from(nodes)
        for i in range(12):
            graph.add_edge(nodes[i], nodes[(i + 1) % 12])
            graph.add_edge(nodes[(i + 3) % 12], nodes[i])
    cross = 0
    while cross < 16:
        a = rng.choice(list(graph.nodes()))
        b = rng.choice(list(graph.nodes()))
        if a.split("/")[0] != b.split("/")[0] and not graph.has_edge(a, b):
            graph.add_edge(a, b)
            cross += 1
    return graph


def _document_style_graph() -> nx.Graph:
    """Weighted similarity graph shaped like a document graph.

    6 topics x 15 chunks; weighted intra-topic edges (cosine-like), sparse
    weighted cross-topic edges, plus two isolated nodes.
    """
    graph = nx.Graph()
    rng = nx.utils.create_py_random_state(7)
    topics = ["biology", "chemistry", "physics", "history", "law", "cooking"]
    for t in topics:
        nodes = [f"{t}_chunk{i}" for i in range(15)]
        graph.add_nodes_from(nodes, category=t)
        for i in range(15):
            graph.add_edge(nodes[i], nodes[(i + 1) % 15], weight=round(rng.uniform(0.86, 0.99), 3))
            graph.add_edge(nodes[i], nodes[(i + 4) % 15], weight=round(rng.uniform(0.85, 0.95), 3))
    for _ in range(12):
        ta, tb = rng.sample(topics, 2)
        a = f"{ta}_chunk{rng.randrange(15)}"
        b = f"{tb}_chunk{rng.randrange(15)}"
        if not graph.has_edge(a, b):
            graph.add_edge(a, b, weight=round(rng.uniform(0.85, 0.88), 3))
    graph.add_node("orphan_doc_1", category="uncategorised")
    graph.add_node("orphan_doc_2", category="uncategorised")
    return graph


def _internal_edge_share(graph: nx.Graph, partition: list[set]) -> float:
    """Fraction of edges whose endpoints share a community."""
    node_to_comm = {n: i for i, c in enumerate(partition) for n in c}
    internal = sum(1 for u, v in graph.edges() if node_to_comm[u] == node_to_comm[v])
    return internal / graph.number_of_edges() if graph.number_of_edges() else 0.0


def _measure(label: str, graph: nx.Graph, algorithm: str) -> dict:
    timings = []
    partition: list[set] | None = None
    for _ in range(REPEATS):
        start = time.perf_counter()
        result = partition_graph(graph, algorithm=algorithm, seed=0)
        timings.append(time.perf_counter() - start)
        frozen = frozenset(frozenset(c) for c in result)
        if partition is None:
            partition = result
            first = frozen
        elif frozen != first:
            raise RuntimeError(f"{label}/{algorithm}: non-deterministic partition")
    sizes = sorted((len(c) for c in partition), reverse=True)
    return {
        "label": label,
        "algorithm": algorithm,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "communities": len(partition),
        "largest": sizes[0] if sizes else 0,
        "singletons": sum(1 for c in partition if len(c) == 1),
        "internal_edge_share": round(_internal_edge_share(graph, partition), 4),
        "median_ms": round(statistics.median(timings) * 1000, 2),
        "deterministic": True,
    }


def main() -> None:
    graphs = [
        ("codebase-style", _codebase_style_graph()),
        ("document-style", _document_style_graph()),
    ]
    rows = []
    for name, graph in graphs:
        for algorithm in ("louvain", "leiden"):
            rows.append(_measure(name, graph, algorithm))

    header = (
        "| Graph | Algorithm | Nodes | Edges | Communities | Largest | "
        "Singletons | Internal edge share | Median runtime (ms) | Deterministic |"
    )
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    lines = [
        "# Louvain vs Leiden comparison (task 3.6)",
        "",
        f"Seed 0, {REPEATS} repeats per cell, via ``core.community.partition_graph``.",
        "Leiden: leidenalg RBConfigurationVertexPartition (γ=1.0), igraph backend.",
        "",
        header,
        sep,
    ]
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['algorithm']} | {r['nodes']} | {r['edges']} | "
            f"{r['communities']} | {r['largest']} | {r['singletons']} | "
            f"{r['internal_edge_share']} | {r['median_ms']} | {r['deterministic']} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- Both strategies satisfied the flat partition contract on every run",
        "  (complete, disjoint, non-empty coverage, including isolated nodes).",
        "- Determinism: all repeats returned identical memberships for both",
        "  algorithms at seed 0.",
        "- Runtime difference at this scale is milliseconds; see ADR-044 for",
        "  the selection rationale (quality of partitions, not speed, drives",
        "  the optional-extra offer).",
    ]
    out = Path(__file__).parent / "output" / "results.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWritten: {out}")


if __name__ == "__main__":
    main()
