"""Behaviour tests for pluggable community detection (OpenSpec tasks 5.2-5.4).

Change: ``add-pluggable-community-detection``. Complements
``test_community_baseline.py`` (tasks 1.1-1.3) with strategy-level
behaviour now the pluggable registry exists:

* Task 5.2 — dispatch. Both registered strategies ("louvain" base and
  "leiden" via the community-leiden extra) run through BOTH consumers
  (``detect_communities`` and ``detect_document_communities``) with
  deterministic membership; an unknown name raises ``KeyError`` at
  dispatch and ``ValueError`` at the composition-root gate; a missing
  extra raises ``ImportError`` (probe and gate) instead of silently
  falling back to Louvain; weighted edges steer grouping for both
  algorithms; isolated nodes are covered exactly once.
* Task 5.3 — boundary purity. The community surface imports no LLM
  (no llama_index, no ``core.providers``) and no algorithm-specific
  object escapes: Leiden results are plain ``list[set]`` of original
  node ids. Base imports stay lazy — importing the consumers and
  compose never loads leidenalg/igraph even with the extra installed.
* Task 5.4-adjacent — registry contract. ``verify_available`` is a
  no-op for probe-less strategies; a register/verify roundtrip with a
  temporary name cleans up after itself.

The community-leiden extra IS installed in this worktree venv, so the
Leiden paths run for real. All graphs are in memory — no Ollama, no
network, no disk.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterable

import networkx as nx
import pytest

import omrg.integrations.leidenalg as leidenalg_adapter

# Enter the codebase package through code_graph (it re-exports the
# detectors): importing communities directly trips a circular import.
from omrg.compose import _validate_community_strategy
from omrg.config import Settings
from omrg.core.codebase.code_graph import detect_communities
from omrg.core.community import partition_graph
from omrg.core.community import registry as community_registry
from omrg.core.documents.doc_graph import detect_document_communities

_REPEATS = 3  # membership repeats for the determinism checks
_ALGORITHMS = ["louvain", "leiden"]

# Base-only CI installations (the floors job) run the fast suite without
# the community-leiden extra; the real-Leiden assertions execute in the
# worktree and the dedicated community-leiden-extra CI job instead.
_LEIDEN_INSTALLED = leidenalg_adapter.is_leiden_available()


def _skip_leiden_without_extra(algorithm: str) -> None:
    """Skip the ``leiden`` parameter when the optional extra is absent."""
    if algorithm == "leiden" and not _LEIDEN_INSTALLED:
        pytest.skip("community-leiden extra not installed")


# Env vars mirroring tests/conftest.py so a subprocess importing compose
# can resolve its embed model without network access (compose runs
# ensure_runtime_setup() at import time).
_BASE_ENV_OVERRIDES = {
    "EMBED_PROVIDER": "local",
    "LOCAL_BACKEND": "ollama",
    "EMBED_MODEL": "nomic-embed-text",
    "OLLAMA_BASE_URL": "http://localhost:11434",
}


# ── Graph builders ───────────────────────────────────────────────────────


def _code_rings(n_rings: int = 4, size: int = 6) -> nx.DiGraph:
    """Build a directed code-style graph of disconnected rings.

    Each ring is one planted community; the consumer converts the
    directed edges to undirected before dispatch.

    Args:
        n_rings: Number of planted ring communities.
        size: Nodes per ring.

    Returns:
        The planted ``nx.DiGraph`` with file-path node ids.
    """
    graph = nx.DiGraph()
    for ring in range(n_rings):
        nodes = [f"src/g{ring}/n{i}.py" for i in range(size)]
        for i in range(size):
            graph.add_edge(nodes[i], nodes[(i + 1) % size])
    return graph


def _code_ring_sets(n_rings: int = 4, size: int = 6) -> list[set[str]]:
    """Return the planted ring node sets for ``_code_rings``."""
    return [{f"src/g{ring}/n{i}.py" for i in range(size)} for ring in range(n_rings)]


def _doc_rings(n_rings: int = 4, size: int = 6) -> nx.Graph:
    """Build an undirected doc-style graph of rings with category attrs.

    Args:
        n_rings: Number of planted ring communities.
        size: Chunk nodes per ring.

    Returns:
        The planted ``nx.Graph``; every node carries ``category="catN"``.
    """
    graph = nx.Graph()
    for ring in range(n_rings):
        nodes = [f"chunk_{ring}_{i}" for i in range(size)]
        graph.add_nodes_from(nodes, category=f"cat{ring}")
        for i in range(size):
            graph.add_edge(nodes[i], nodes[(i + 1) % size])
    return graph


def _doc_ring_sets(n_rings: int = 4, size: int = 6) -> list[set[str]]:
    """Return the planted ring node sets for ``_doc_rings``."""
    return [{f"chunk_{ring}_{i}" for i in range(size)} for ring in range(n_rings)]


def _weighted_planted() -> tuple[nx.Graph, set[str], set[str]]:
    """Two 6-cliques with heavy intra-group weights and a light cross ring.

    Intra-group edges carry weight 0.95; the cross edges 0.86. Both
    weights are positive (RBConfigurationVertexPartition requires
    positive weights) and the gap is wide enough that the planted split
    is the modularity optimum for both strategies.

    Returns:
        ``(graph, group_a, group_b)`` node-set triple.
    """
    graph = nx.Graph()
    a = [f"a{i}" for i in range(6)]
    b = [f"b{i}" for i in range(6)]
    graph.add_nodes_from(a + b)
    for group in (a, b):
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                graph.add_edge(group[i], group[j], weight=0.95)
    for i in range(len(a)):
        graph.add_edge(a[i], b[i], weight=0.86)
    return graph, set(a), set(b)


def _ring_plus_isolated() -> nx.Graph:
    """One 6-node ring plus two degree-0 nodes (8 nodes total)."""
    graph = nx.Graph()
    nodes = [f"n{i}" for i in range(6)]
    graph.add_nodes_from(nodes)
    for i in range(6):
        graph.add_edge(nodes[i], nodes[(i + 1) % 6])
    graph.add_nodes_from(["iso1", "iso2"])
    return graph


def _membership_signature(groups: Iterable[Iterable[str]]) -> frozenset[frozenset[str]]:
    """Canonical order-insensitive partition signature.

    Args:
        groups: Per-community node collections (``files``/``chunks``).

    Returns:
        A hashable signature for equality across repeated runs.
    """
    return frozenset(frozenset(group) for group in groups)


def _run_python(code: str, *, with_env_overrides: bool = False) -> subprocess.CompletedProcess:
    """Run an import-purity probe in a clean interpreter.

    A subprocess is required because the pytest process itself imports
    llama_index (conftest patches MockEmbedding) and runs real Leiden
    partitions, so in-process ``sys.modules`` checks cannot observe the
    base import surface.

    Args:
        code: Python source executed via ``python -c``.
        with_env_overrides: Apply the conftest env vars (needed when the
            probe imports ``omrg.compose``, whose import-time
            ``ensure_runtime_setup()`` resolves an embed model).

    Returns:
        The completed subprocess (check ``returncode``/``stderr``).
    """
    env = dict(os.environ)
    if with_env_overrides:
        env.update(_BASE_ENV_OVERRIDES)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


# ── Task 5.2 — both strategies through both consumers ────────────────────


class TestDispatchThroughConsumers:
    """Task 5.2 — louvain and leiden both serve the code and doc graphs."""

    @pytest.mark.parametrize("algorithm", _ALGORITHMS)
    def test_detect_communities_runs_both_strategies(self, effective_settings, algorithm):
        """The code-graph consumer recovers the planted rings for both strategies."""
        _skip_leiden_without_extra(algorithm)
        graph = _code_rings()
        communities = detect_communities(
            graph, settings=effective_settings(community_algorithm=algorithm)
        )

        rings = _code_ring_sets()
        assert len(communities) == len(rings)
        # Every node covered exactly once (sorted flatten catches repeats).
        covered = [f for community in communities for f in community.files]
        assert sorted(covered) == sorted(graph.nodes())
        # Each detected community is exactly one planted ring.
        for community in communities:
            assert set(community.files) in rings

    @pytest.mark.parametrize("algorithm", _ALGORITHMS)
    def test_detect_communities_membership_repeatable(self, effective_settings, algorithm):
        """Seeded repeats return the same membership for both strategies."""
        _skip_leiden_without_extra(algorithm)
        graph = _code_rings()
        signatures = set()
        for _ in range(_REPEATS):
            communities = detect_communities(
                graph, settings=effective_settings(community_algorithm=algorithm)
            )
            signatures.add(_membership_signature([c.files for c in communities]))
        assert len(signatures) == 1

    @pytest.mark.parametrize("algorithm", _ALGORITHMS)
    def test_detect_document_communities_runs_both_strategies(self, effective_settings, algorithm):
        """The doc-graph consumer recovers the rings and propagates categories."""
        _skip_leiden_without_extra(algorithm)
        graph = _doc_rings()
        communities = detect_document_communities(
            graph, settings=effective_settings(community_algorithm=algorithm)
        )

        rings = _doc_ring_sets()
        assert len(communities) == len(rings)
        covered = [chunk for community in communities for chunk in community.chunks]
        assert sorted(covered) == sorted(graph.nodes())
        ring_categories = {f"cat{ring}" for ring in range(4)}
        for community in communities:
            assert set(community.chunks) in rings
            # Category-bearing communities adopt the ring's category as label.
            assert community.category in ring_categories
            assert community.label == community.category

    @pytest.mark.parametrize("algorithm", _ALGORITHMS)
    def test_detect_document_communities_membership_repeatable(self, effective_settings, algorithm):
        """Seeded repeats return the same doc-graph membership for both strategies."""
        _skip_leiden_without_extra(algorithm)
        graph = _doc_rings()
        signatures = set()
        for _ in range(_REPEATS):
            communities = detect_document_communities(
                graph, settings=effective_settings(community_algorithm=algorithm)
            )
            signatures.add(_membership_signature([c.chunks for c in communities]))
        assert len(signatures) == 1


# ── Task 5.2 — unknown names fail loudly ──────────────────────────────────


def test_partition_graph_unknown_algorithm_lists_registered_names():
    """Dispatch raises ``KeyError`` naming both registered strategies."""
    graph = _ring_plus_isolated()
    with pytest.raises(
        KeyError,
        match=r"Unknown community strategy 'spectral'. "
        r"Available: \['leiden', 'louvain'\]",
    ):
        partition_graph(graph, algorithm="spectral", seed=0)
    assert set(community_registry.available()) == {"louvain", "leiden"}


def test_compose_gate_rejects_unknown_strategy():
    """The composition-root gate fails startup listing the registered names."""
    settings = Settings(_env_file=None, community_algorithm="spectral")
    with pytest.raises(
        ValueError,
        match=r"COMMUNITY_ALGORITHM='spectral' is not a registered community "
        r"strategy. Available: leiden, louvain.",
    ):
        _validate_community_strategy(settings)


def test_compose_gate_accepts_registered_strategies():
    """Both registered names pass the startup gate when their deps are present."""
    for name in ("louvain", "leiden"):
        if name == "leiden" and not _LEIDEN_INSTALLED:
            # The unavailable-extra failure path is covered by the
            # missing-extra tests below; nothing to accept without the extra.
            continue
        _validate_community_strategy(Settings(_env_file=None, community_algorithm=name))


def test_compose_gate_blank_value_resets_to_default():
    """``COMMUNITY_ALGORITHM=''`` (or whitespace) resets to the louvain default."""
    _validate_community_strategy(Settings(_env_file=None, community_algorithm="  "))


# ── Task 5.2 — a missing extra fails loudly (no silent fallback) ──────────


class TestMissingExtraFails:
    """Task 5.2 — selecting leiden without the extra raises, never falls back."""

    def test_registry_probe_raises_import_error(self, monkeypatch):
        """The registered probe raises with the installation instruction."""
        monkeypatch.setattr(leidenalg_adapter, "is_leiden_available", lambda: False)
        with pytest.raises(ImportError, match="community-leiden"):
            community_registry.verify_available("leiden")

    def test_compose_gate_raises_import_error(self, monkeypatch):
        """The startup gate propagates the probe's ImportError (no fallback)."""
        monkeypatch.setattr(leidenalg_adapter, "is_leiden_available", lambda: False)
        settings = Settings(_env_file=None, community_algorithm="leiden")
        with pytest.raises(ImportError, match="community-leiden"):
            _validate_community_strategy(settings)


# ── Task 5.2 — shared graph semantics: weights and isolated nodes ─────────


class TestPartitionBehaviour:
    """Task 5.2 — weighted and isolated-node graphs behave for both strategies."""

    @pytest.mark.parametrize("algorithm", _ALGORITHMS)
    def test_weighted_edges_steer_grouping(self, algorithm):
        """Heavy intra-group weights make both strategies recover the planted split."""
        _skip_leiden_without_extra(algorithm)
        graph, group_a, group_b = _weighted_planted()
        result = partition_graph(graph, algorithm=algorithm, seed=0)
        assert {frozenset(community) for community in result} == {
            frozenset(group_a),
            frozenset(group_b),
        }

    @pytest.mark.parametrize("algorithm", _ALGORITHMS)
    def test_isolated_nodes_covered_exactly_once(self, algorithm):
        """Degree-0 nodes join the partition exactly once, as singleton communities."""
        _skip_leiden_without_extra(algorithm)
        graph = _ring_plus_isolated()
        result = partition_graph(graph, algorithm=algorithm, seed=0)
        # Sorted flatten catches both missing and duplicated nodes.
        assert sorted(n for community in result for n in community) == sorted(graph.nodes())
        # Isolated nodes are the modularity-optimal singletons for both
        # strategies (leiden maps them via the membership array).
        assert {"iso1"} in result
        assert {"iso2"} in result


# ── Task 5.3 — boundary purity: no LLM, no algorithm objects escape ───────


class TestBoundaryPurity:
    """Task 5.3 — the community surface stays LLM-free and type-clean."""

    def test_import_surface_has_no_llm(self):
        """Importing the community surface pulls no llama_index or providers modules."""
        code = (
            "import sys\n"
            "import omrg.core.community\n"
            # code_graph first: importing communities directly trips a
            # circular import (communities -> code_graph -> communities).
            "import omrg.core.codebase.code_graph\n"
            "import omrg.core.codebase.communities\n"
            "import omrg.core.documents.doc_graph\n"
            "import omrg.integrations.leidenalg\n"
            "llama = sorted(m for m in sys.modules"
            " if m == 'llama_index' or m.startswith('llama_index.'))\n"
            "providers = sorted(m for m in sys.modules"
            " if m.startswith('omrg.core.providers'))\n"
            "assert not llama, f'llama_index leaked into base imports: {llama[:5]}'\n"
            "assert not providers, f'providers leaked into base imports: {providers[:5]}'\n"
        )
        completed = _run_python(code)
        assert completed.returncode == 0, completed.stderr

    @pytest.mark.skipif(not _LEIDEN_INSTALLED, reason="community-leiden extra not installed")
    def test_leiden_returns_plain_python_partition(self):
        """Leiden results are ``list[set]`` of original node ids — no igraph types."""
        graph = _code_rings().to_undirected()
        result = partition_graph(graph, algorithm="leiden", seed=0)

        assert isinstance(result, list)
        assert all(isinstance(community, set) for community in result)
        # Every element is an original (hashable str) node id, and the
        # union covers the graph — no igraph Vertex/VertexSeq escapes.
        assert {node for community in result for node in community} == set(graph.nodes())
        assert all(isinstance(node, str) for community in result for node in community)

    def test_base_imports_do_not_load_leidenalg_or_igraph(self):
        """Even with the extra installed, base imports stay lazy (design decision 3)."""
        code = (
            "import sys\n"
            "import omrg.core.community\n"
            "import omrg.core.community.registry\n"
            "import omrg.core.codebase.code_graph\n"
            "import omrg.core.codebase.communities\n"
            "import omrg.core.documents.doc_graph\n"
            "import omrg.compose\n"
            "heavy = [m for m in ('leidenalg', 'igraph') if m in sys.modules]\n"
            "assert not heavy, f'optional-extra modules loaded at import time: {heavy}'\n"
        )
        completed = _run_python(code, with_env_overrides=True)
        assert completed.returncode == 0, completed.stderr


# ── Task 5.4-adjacent — registry contract ─────────────────────────────────


class TestRegistryContract:
    """Task 5.4-adjacent — probe-less pass; register/verify roundtrip is clean."""

    def test_verify_available_louvain_is_noop(self):
        """Louvain registers no probe, so verification passes unconditionally."""
        # Returns None without raising — no optional dependency to check.
        assert community_registry.verify_available("louvain") is None

    def test_register_and_verify_roundtrip_cleans_up(self):
        """A temporary strategy registers, verifies, resolves, and is removed."""
        fake = "test-fake-strategy"
        assert fake not in community_registry.available()
        try:
            community_registry.register(fake, "omrg.core.community.louvain:partition")
            assert fake in community_registry.available()
            # No availability probe registered → verification is a no-op.
            community_registry.verify_available(fake)
            from omrg.core.community import louvain as louvain_strategy

            assert community_registry.get(fake) is louvain_strategy.partition
        finally:
            # The registry has no unregister(); pop the temp entries so
            # later tests (and `available()` listings) stay clean.
            community_registry._registry.pop(fake, None)
            community_registry._cache.pop(fake, None)
        assert fake not in community_registry.available()


# ── Partition-contract validation (spec: one partition contract) ─────────


class TestPartitionContractValidation:
    """``validate_partition`` rejects every contract violation by name.

    These branches are the teeth of the "no algorithm-specific object
    escapes" scenario — a strategy returning igraph types, empty sets,
    overlapping memberships, or partial coverage fails at the boundary,
    never inside a consumer's formatting loop.
    """

    def test_rejects_non_list_or_non_set_result(self):
        """A tuple of frozensets (igraph-style) is rejected with a type error."""
        from omrg.core.community import validate_partition

        with pytest.raises(ValueError, match="list\\[set\\[Hashable\\]\\]"):
            validate_partition((frozenset({"a"}),), {"a"})

    def test_rejects_empty_community(self):
        """An empty community set violates the non-empty rule."""
        from omrg.core.community import validate_partition

        with pytest.raises(ValueError, match="empty community"):
            validate_partition([{"a"}, set()], {"a"})

    def test_rejects_overlapping_communities(self):
        """A node in two communities violates the disjoint rule."""
        from omrg.core.community import validate_partition

        with pytest.raises(ValueError, match="more than\\s+one community"):
            validate_partition([{"a", "b"}, {"b", "c"}], {"a", "b", "c"})

    def test_rejects_incomplete_coverage(self):
        """A partition missing input nodes violates the complete rule."""
        from omrg.core.community import validate_partition

        with pytest.raises(ValueError, match="complete coverage"):
            validate_partition([{"a"}], {"a", "z"})
