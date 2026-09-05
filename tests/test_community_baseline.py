"""Baseline and contract tests for community detection (OpenSpec tasks 1.1-1.3).

Change: ``add-pluggable-community-detection``. TEST-FIRST tests locking
the behaviour the pluggable strategy work must preserve:

* Task 1.1 — determinism gap. The seed-capture tests PASS today and
  document that ``louvain_communities`` is called without a ``seed``
  kwarg; task 2.2 flips them to require ``seed == 0``. The
  repeatable-membership tests lock determinism for the future; they may
  fail today (the documented gap) or pass accidentally pre-fix.
* Task 1.2 — shared partition contract: every node in exactly one
  non-empty community; <5 nodes keep the single-community bypass; an
  empty document graph returns ``[]``.
* Task 1.3 — output-shape recording: labels, sort orders, edge counts,
  hub/bridge shape (spec: "Graph consumer behaviour is preserved").

All graphs are in memory — no Ollama, no network, no disk.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable

import networkx as nx
import pytest

# Enter through code_graph (its __all__ re-exports the detectors):
# importing communities directly trips a circular import.
from omrg.core.codebase.code_graph import (
    detect_bridges,
    detect_communities,
    detect_hubs,
)
from omrg.core.documents.doc_graph import detect_document_communities

_REPEATS = 30  # runs for the task 1.1 determinism tests


# ── Graph builders ───────────────────────────────────────────────────────


def _planted_code_graph(
    n_groups: int = 4,
    group_size: int = 10,
    cross_pairs: int = 5,
    rng_seed: int = 7,
) -> nx.DiGraph:
    """Build a DiGraph with a planted community structure plus noise edges.

    Each group is a circulant ring (steps 1 and 2), so intra-group density
    far exceeds inter-group density. The bidirectional cross-group pairs
    add tie-breaking pressure that can expose the missing seed.

    Args:
        n_groups: Number of planted groups.
        group_size: Nodes per group.
        cross_pairs: Number of cross-group node pairs to link.
        rng_seed: Seed for the builder's RNG (test scaffolding — not
            Louvain's seed).

    Returns:
        A directed graph with ``n_groups * group_size`` nodes.
    """
    rng = random.Random(rng_seed)  # noqa: S311 - test fixture builder, not crypto
    graph = nx.DiGraph()
    groups: list[list[str]] = []
    for g in range(n_groups):
        nodes = [f"pkg{g}/mod{i}.py" for i in range(group_size)]
        groups.append(nodes)
        graph.add_nodes_from(nodes)
        for i in range(group_size):
            graph.add_edge(nodes[i], nodes[(i + 1) % group_size])
            graph.add_edge(nodes[(i + 2) % group_size], nodes[i])

    # Bidirectional noise edges between groups (never within a group).
    added = 0
    while added < cross_pairs:
        src = rng.choice(rng.choice(groups))
        dst = rng.choice(rng.choice(groups))
        if src == dst or src.rsplit("/", 1)[0] == dst.rsplit("/", 1)[0]:
            continue
        graph.add_edge(src, dst)
        graph.add_edge(dst, src)
        added += 1
    return graph


def _two_disjoint_cliques() -> nx.DiGraph:
    """Build two fully bidirectional 5-cliques with no cross edges.

    Louvain never merges disconnected components, so the partition is
    known regardless of randomisation. Each clique holds 5 x 4 = 20
    directed edges — a hand-countable internal edge total.

    Returns: Directed graph, cliques ``alpha/a-e.py`` and ``beta/f-j.py``.
    """
    graph = nx.DiGraph()
    for prefix, letters in (("alpha", "abcde"), ("beta", "fghij")):
        nodes = [f"{prefix}/{letter}.py" for letter in letters]
        for u in nodes:
            for v in nodes:
                if u != v:
                    graph.add_edge(u, v)
    return graph


def _categorised_doc_graph() -> nx.Graph:
    """Build two disconnected 6-node rings carrying category attributes.

    Group ``x`` mixes categories 4:2 so the most-common rule is testable;
    group ``y`` is single-category. Rings share no edges, so Louvain
    returns one community per group.

    Returns:
        Undirected graph whose nodes carry a ``category`` attribute.
    """
    graph = nx.Graph()
    x_cats = ["biology"] * 4 + ["chemistry"] * 2
    x_nodes = [f"x{i}" for i in range(6)]
    for node, cat in zip(x_nodes, x_cats, strict=True):
        graph.add_node(node, category=cat)
    y_nodes = [f"y{i}" for i in range(6)]
    for node in y_nodes:
        graph.add_node(node, category="physics")
    for ring in (x_nodes, y_nodes):
        for i in range(6):
            graph.add_edge(ring[i], ring[(i + 1) % 6])
    return graph


def _membership(groups: Iterable[Iterable[str]]) -> frozenset[frozenset[str]]:
    """Convert per-community node collections into a partition signature.

    Args:
        groups: Per-community file or chunk collections.

    Returns:
        Frozenset of frozensets, comparable across repeated runs.
    """
    return frozenset(frozenset(g) for g in groups)


# ── Task 1.1: determinism gap regression ────────────────────────────────


def _capture_louvain_kwargs(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Patch ``louvain_communities`` to record its kwargs and delegate.

    Returns:
        A list that receives one kwargs dict per observed call.
    """
    real_louvain = nx.algorithms.community.louvain_communities
    captured: list[dict] = []

    def spying_louvain(graph, **kwargs):
        captured.append(kwargs)
        return real_louvain(graph, **kwargs)

    monkeypatch.setattr(nx.algorithms.community, "louvain_communities", spying_louvain)
    return captured


def test_detect_communities_passes_default_seed_to_louvain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 1.1 → 2.2 (flipped): the default seed ``0`` reaches Louvain.

    Spec: "Louvain uses the default seed" — seed 0 when no operator seed
    is configured.  Before task 2.2 this test asserted the opposite (no
    seed kwarg) to document the determinism gap.
    """
    captured = _capture_louvain_kwargs(monkeypatch)
    detect_communities(_planted_code_graph())
    assert len(captured) == 1
    assert captured[0].get("seed") == 0, (
        "detect_communities must pass seed=0 (the configured default) to "
        "louvain_communities so partitions are deterministic"
    )


def test_detect_document_communities_passes_default_seed_to_louvain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 1.1 → 2.2 (flipped): the default seed ``0`` reaches Louvain."""
    captured = _capture_louvain_kwargs(monkeypatch)
    detect_document_communities(_planted_code_graph().to_undirected())
    assert len(captured) == 1
    assert captured[0].get("seed") == 0, (
        "detect_document_communities must pass seed=0 (the configured "
        "default) to louvain_communities so partitions are deterministic"
    )


def test_detect_communities_membership_repeatable_across_runs() -> None:
    """Task 1.1 (Test B): repeated code-graph partitions must be identical.

    Spec scenario "Same graph and seed are repeated". May FAIL today (the
    documented unseeded gap) or pass accidentally pre-fix; must pass
    deterministically once task 2.2 passes ``seed=0``.
    """
    graph = _planted_code_graph()
    partitions = {
        _membership(comm.files for comm in detect_communities(graph)) for _ in range(_REPEATS)
    }
    assert len(partitions) == 1, (
        f"detect_communities produced {len(partitions)} distinct "
        f"partitions across {_REPEATS} runs on the same graph — the "
        "unseeded-Louvain determinism gap (task 2.2 passes seed=0)"
    )


def test_detect_document_communities_membership_repeatable_across_runs() -> None:
    """Task 1.1 (Test B): repeated doc-graph partitions must be identical.

    Same forward-locking contract as the code-graph variant: may fail
    today, must pass once task 2.2 lands the default seed.
    """
    graph = _planted_code_graph().to_undirected()
    partitions = {
        _membership(comm.chunks for comm in detect_document_communities(graph))
        for _ in range(_REPEATS)
    }
    assert len(partitions) == 1, (
        f"detect_document_communities produced {len(partitions)} distinct "
        f"partitions across {_REPEATS} runs on the same graph — the "
        "unseeded-Louvain determinism gap (task 2.2 passes seed=0)"
    )


# ── Task 1.2: shared partition contract ─────────────────────────────────


def test_detect_communities_partition_covers_each_node_once() -> None:
    """Task 1.2: the flat partition is disjoint, complete, non-empty.

    Spec scenario "A graph is partitioned successfully": union of the
    returned communities equals the input node set and no node appears
    in more than one community.
    """
    graph = _planted_code_graph()
    nodes = set(graph.nodes())
    result = detect_communities(graph)
    seen = [f for comm in result for f in comm.files]
    assert set(seen) == nodes
    assert len(seen) == len(nodes)  # disjoint: no duplicates anywhere
    assert all(comm.files for comm in result)  # no empty community


def test_detect_document_communities_partition_covers_each_node_once() -> None:
    """Task 1.2: the doc-graph flat partition is disjoint and complete."""
    graph = _planted_code_graph().to_undirected()
    nodes = set(graph.nodes())
    result = detect_document_communities(graph)
    seen = [chunk for comm in result for chunk in comm.chunks]
    assert set(seen) == nodes
    assert len(seen) == len(nodes)
    assert all(comm.chunks for comm in result)


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_detect_communities_small_graph_single_community(n: int) -> None:
    """Task 1.2: graphs under five nodes keep the single-community bypass.

    Spec scenario "A small graph bypasses partitioning" — the existing
    behaviour must remain unchanged for 1-4 nodes.
    """
    graph = nx.DiGraph()
    nodes = [f"s/a{i}.py" for i in range(1, n + 1)]
    graph.add_nodes_from(nodes)
    for i in range(n - 1):
        graph.add_edge(nodes[i], nodes[i + 1])

    result = detect_communities(graph)

    assert len(result) == 1
    assert set(result[0].files) == set(nodes)
    # Bypass edge_count is the whole graph's edge count, not internal-only.
    assert result[0].edge_count == graph.number_of_edges() == n - 1


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_detect_document_communities_small_graph_single_community(n: int) -> None:
    """Task 1.2: doc graphs under five nodes keep the single-community bypass."""
    graph = nx.Graph()
    nodes = [f"c{i}" for i in range(1, n + 1)]
    graph.add_nodes_from(nodes)
    for i in range(n - 1):
        graph.add_edge(nodes[i], nodes[i + 1])

    result = detect_document_communities(graph)

    assert len(result) == 1
    assert set(result[0].chunks) == set(nodes)


def test_detect_document_communities_empty_graph_returns_empty_list() -> None:
    """Task 1.2: a zero-node document graph returns an empty list."""
    assert detect_document_communities(nx.Graph()) == []


def test_detect_communities_small_graph_label_and_edge_count() -> None:
    """Task 1.3 (shape): the bypass label joins first-3 file NAMES, comma-space."""
    graph = nx.DiGraph()
    nodes = ["s/a1.py", "s/a2.py", "s/a3.py", "s/a4.py"]
    graph.add_nodes_from(nodes)
    for i in range(3):
        graph.add_edge(nodes[i], nodes[i + 1])

    result = detect_communities(graph)

    assert len(result) == 1
    # Names (not stems), comma + space, insertion order of first three.
    assert result[0].label == "a1.py, a2.py, a3.py"
    assert result[0].edge_count == 3


def test_detect_document_communities_small_graph_label_from_first_category() -> None:
    """Task 1.3 (shape): bypass label uses the FIRST category in node order.

    Unlike the >=5 path (most common category), the <5 bypass takes the
    first non-empty category in insertion order.
    """
    graph = nx.Graph()
    graph.add_node("c1")
    graph.add_node("c2", category="physics")
    graph.add_node("c3", category="math")
    graph.add_edge("c1", "c2")
    graph.add_edge("c2", "c3")

    result = detect_document_communities(graph)

    assert len(result) == 1
    assert result[0].label == "physics"
    assert result[0].category == "physics"


def test_detect_document_communities_small_graph_label_all_without_categories() -> None:
    """Task 1.3 (shape): bypass label falls back to "all" with no categories."""
    graph = nx.Graph()
    graph.add_edges_from([("c1", "c2"), ("c2", "c3")])

    result = detect_document_communities(graph)

    assert len(result) == 1
    assert result[0].label == "all"
    assert result[0].category == ""


# ── Task 1.3: output-shape recording (>=5 nodes) ────────────────────────


def test_detect_communities_files_sorted_and_size_descending() -> None:
    """Task 1.3: files sorted within community; communities by size desc."""
    result = detect_communities(_planted_code_graph())
    assert len(result) >= 2  # planted structure must split
    for comm in result:
        assert comm.files == sorted(comm.files)
        assert comm.files  # non-empty
        assert isinstance(comm.label, str) and comm.label
    sizes = [len(comm.files) for comm in result]
    assert sizes == sorted(sizes, reverse=True)


def test_detect_communities_label_is_top_three_sorted_stems() -> None:
    """Task 1.3: label is "/".join of the top-3 stems in sorted order.

    Uses disjoint cliques so the partition is known: alpha sorts to
    a, b, c, d, e (label "a/b/c") and beta to f, g, h, i, j ("f/g/h").
    """
    result = detect_communities(_two_disjoint_cliques())
    assert len(result) == 2
    assert {comm.label for comm in result} == {"a/b/c", "f/g/h"}


def test_detect_communities_edge_count_counts_internal_directed_edges() -> None:
    """Task 1.3: edge_count equals internal DIRECTED edge count.

    Hand-counted check on disjoint 5-cliques (5 x 4 = 20 ordered pairs
    each) plus a derived check recomputed from returned membership.
    """
    clique_result = detect_communities(_two_disjoint_cliques())
    assert len(clique_result) == 2
    assert [comm.edge_count for comm in clique_result] == [20, 20]

    planted = _planted_code_graph()
    for comm in detect_communities(planted):
        members = set(comm.files)
        expected = sum(1 for u, v in planted.edges() if u in members and v in members)
        assert comm.edge_count == expected


def test_detect_document_communities_chunks_sorted_and_size_descending() -> None:
    """Task 1.3: chunks sorted within community; communities by size desc."""
    result = detect_document_communities(_categorised_doc_graph())
    assert len(result) == 2
    for comm in result:
        assert comm.chunks == sorted(comm.chunks)
        assert comm.chunks
        assert isinstance(comm.label, str) and comm.label
    sizes = [len(comm.chunks) for comm in result]
    assert sizes == sorted(sizes, reverse=True)


def test_detect_document_communities_label_is_most_common_category() -> None:
    """Task 1.3: >=5-node label is the most common category; label == category.

    Group x mixes biology (4) vs chemistry (2) so the Counter-based rule
    is exercised, not just "any category present".
    """
    result = detect_document_communities(_categorised_doc_graph())
    by_node = {chunk: comm for comm in result for chunk in comm.chunks}

    x_comm = by_node["x1"]
    assert x_comm.category == "biology"
    assert x_comm.label == "biology"

    y_comm = by_node["y1"]
    assert y_comm.category == "physics"
    assert y_comm.label == "physics"


def test_detect_document_communities_topic_fallback_without_categories() -> None:
    """Task 1.3: uncategorised nodes label communities "Topic N".

    Exact numbering depends on pre-sort iteration order, so only the
    shape is locked: regex match on the label and an empty category.
    """
    graph = _two_disjoint_cliques().to_undirected()
    result = detect_document_communities(graph)
    assert len(result) == 2
    for comm in result:
        assert comm.category == ""
        assert re.fullmatch(r"Topic \d+", comm.label)


def test_detect_hubs_sorted_by_in_degree_descending() -> None:
    """Task 1.3 (smoke): hubs sorted by in-degree descending.

    Graph layout (20 nodes so the top-10% threshold index is 2):
    hub_a in-degree 5, hub_b and hub_c in-degree 4, four isolated nodes,
    and 13 distinct source nodes. Sorted in-degrees [5, 4, 4, 0, ...]
    give threshold min(4, 5) = 4, so exactly the three hubs qualify.
    """
    graph = nx.DiGraph()
    for iso in ("iso1", "iso2", "iso3", "iso4"):
        graph.add_node(iso)
    for i in range(1, 6):
        graph.add_edge(f"src_a{i}.py", "hub_a.py")
    for i in range(1, 5):
        graph.add_edge(f"src_b{i}.py", "hub_b.py")
        graph.add_edge(f"src_c{i}.py", "hub_c.py")

    hubs = detect_hubs(graph)

    assert {hub.file for hub in hubs} == {"hub_a.py", "hub_b.py", "hub_c.py"}
    degrees = [hub.in_degree for hub in hubs]
    assert degrees == sorted(degrees, reverse=True)
    assert hubs[0].file == "hub_a.py"
    assert hubs[0].in_degree == 5


def test_detect_bridges_span_at_least_two_communities() -> None:
    """Task 1.3 (smoke): bridges reference >=2 sorted community indices.

    Two 5-cliques joined by a single weak cross pair: only the cross
    endpoints (a1, b1) carry betweenness, each spanning {0, 1}.
    """
    graph = nx.DiGraph()
    groups = (
        [f"m/a{i}.py" for i in range(1, 6)],
        [f"m/b{i}.py" for i in range(1, 6)],
    )
    for group in groups:
        for u in group:
            for v in group:
                if u != v:
                    graph.add_edge(u, v)
    graph.add_edge(groups[0][0], groups[1][0])
    graph.add_edge(groups[1][0], groups[0][0])

    communities = detect_communities(graph)
    assert len(communities) == 2

    bridges = detect_bridges(graph, communities)

    assert {bridge.file for bridge in bridges} == {"m/a1.py", "m/b1.py"}
    for bridge in bridges:
        assert bridge.betweenness > 0
        assert len(bridge.communities) >= 2
        assert bridge.communities == sorted(bridge.communities)
        assert set(bridge.communities) == {0, 1}
    scores = [bridge.betweenness for bridge in bridges]
    assert scores == sorted(scores, reverse=True)
