"""Unit tests for doc_graph.py — similarity edges, metadata edges, heading edges, community detection, cross-links."""

from __future__ import annotations

from unittest.mock import MagicMock

import networkx as nx
import numpy as np
import pytest

from rag_mcp.core.documents.doc_graph import (
    CrossLink,
    DocCommunity,
    Edge,
    build_document_graph,
    compute_cross_links,
    compute_heading_edges,
    compute_metadata_edges,
    compute_similarity_edges,
    detect_document_communities,
)


# ── Helper: create a mock ChromaDB collection ────────────────────────────


def _make_mock_collection(
    ids: list[str],
    embeddings: list[list[float]] | None = None,
    metadatas: list[dict] | None = None,
) -> MagicMock:
    """Create a mock ChromaDB collection with get() support."""
    collection = MagicMock()
    result = {"ids": ids}
    if embeddings is not None:
        result["embeddings"] = embeddings
    if metadatas is not None:
        result["metadatas"] = metadatas
    collection.get.return_value = result
    return collection


# ── Similarity edge tests ────────────────────────────────────────────────


class TestComputeSimilarityEdges:
    """Tests for embedding similarity edge computation."""

    def test_high_similarity_connected(self) -> None:
        """Chunks with similarity above threshold get edges."""
        ids = ["chunk1", "chunk2"]
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.99, 0.01, 0.0],  # Very similar to chunk1
        ]
        metadatas = [
            {"content_type": "document/markdown"},
            {"content_type": "document/markdown"},
        ]
        collection = _make_mock_collection(ids, embeddings, metadatas)
        edges = compute_similarity_edges(collection, threshold=0.85)
        assert len(edges) == 1
        assert edges[0].relation == "similar"
        assert edges[0].weight >= 0.85

    def test_below_threshold_not_connected(self) -> None:
        """Chunks below threshold don't get edges."""
        ids = ["chunk1", "chunk2"]
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],  # Orthogonal — similarity ~0
        ]
        metadatas = [
            {"content_type": "document/markdown"},
            {"content_type": "document/markdown"},
        ]
        collection = _make_mock_collection(ids, embeddings, metadatas)
        edges = compute_similarity_edges(collection, threshold=0.85)
        assert len(edges) == 0

    def test_code_chunks_excluded(self) -> None:
        """Code-type chunks are not included in similarity computation."""
        ids = ["chunk1", "chunk2"]
        embeddings = [
            [1.0, 0.0],
            [0.99, 0.01],
        ]
        metadatas = [
            {"content_type": "code/python"},
            {"content_type": "code/python"},
        ]
        collection = _make_mock_collection(ids, embeddings, metadatas)
        edges = compute_similarity_edges(collection, threshold=0.85)
        assert len(edges) == 0

    def test_none_collection(self) -> None:
        """None collection returns empty list."""
        edges = compute_similarity_edges(None)
        assert edges == []

    def test_single_chunk_no_edges(self) -> None:
        """Single chunk produces no edges."""
        ids = ["chunk1"]
        embeddings = [[1.0, 0.0]]
        metadatas = [{"content_type": "document/markdown"}]
        collection = _make_mock_collection(ids, embeddings, metadatas)
        edges = compute_similarity_edges(collection)
        assert edges == []


# ── Metadata edge tests ──────────────────────────────────────────────────


class TestComputeMetadataEdges:
    """Tests for metadata category and keyword edges."""

    def test_same_category_connected(self) -> None:
        """Chunks with same category get an edge."""
        ids = ["chunk1", "chunk2"]
        metadatas = [
            {"content_type": "document/markdown", "category": "security"},
            {"content_type": "document/markdown", "category": "security"},
        ]
        collection = _make_mock_collection(ids, None, metadatas)
        edges = compute_metadata_edges(collection)
        category_edges = [e for e in edges if e.relation == "category"]
        assert len(category_edges) == 1
        assert category_edges[0].weight == 1.0

    def test_different_category_no_edge(self) -> None:
        """Chunks with different categories don't get category edges."""
        ids = ["chunk1", "chunk2"]
        metadatas = [
            {"content_type": "document/markdown", "category": "security"},
            {"content_type": "document/markdown", "category": "api"},
        ]
        collection = _make_mock_collection(ids, None, metadatas)
        edges = compute_metadata_edges(collection)
        category_edges = [e for e in edges if e.relation == "category"]
        assert len(category_edges) == 0

    def test_shared_keywords_connected(self) -> None:
        """Chunks with shared keywords get a keyword edge."""
        ids = ["chunk1", "chunk2"]
        metadatas = [
            {"content_type": "document/markdown", "keywords": ["redis", "session", "auth"]},
            {"content_type": "document/markdown", "keywords": ["redis", "cache", "ttl"]},
        ]
        collection = _make_mock_collection(ids, None, metadatas)
        edges = compute_metadata_edges(collection)
        keyword_edges = [e for e in edges if e.relation == "keyword"]
        assert len(keyword_edges) == 1
        assert "redis" in keyword_edges[0].shared_keywords
        assert keyword_edges[0].weight == 0.5

    def test_no_shared_metadata(self) -> None:
        """Chunks with no shared metadata get no edges."""
        ids = ["chunk1", "chunk2"]
        metadatas = [
            {"content_type": "document/markdown", "category": "a", "keywords": ["x"]},
            {"content_type": "document/markdown", "category": "b", "keywords": ["y"]},
        ]
        collection = _make_mock_collection(ids, None, metadatas)
        edges = compute_metadata_edges(collection)
        assert len(edges) == 0


# ── Heading edge tests ───────────────────────────────────────────────────


class TestComputeHeadingEdges:
    """Tests for heading hierarchy edge computation."""

    def test_heading_parent_child(self) -> None:
        """Parent heading chunks connect to children."""
        ids = ["chunk1", "chunk2", "chunk3"]
        metadatas = [
            {"content_type": "document/markdown", "header_path": "API"},
            {"content_type": "document/markdown", "header_path": "API/Authentication"},
            {"content_type": "document/markdown", "header_path": "API/Rate Limiting"},
        ]
        collection = _make_mock_collection(ids, None, metadatas)
        edges = compute_heading_edges(collection)
        assert len(edges) >= 2
        for edge in edges:
            assert edge.relation == "heading_child"

    def test_no_heading_metadata(self) -> None:
        """Chunks without header_path produce no heading edges."""
        ids = ["chunk1", "chunk2"]
        metadatas = [
            {"content_type": "document/markdown"},
            {"content_type": "document/markdown"},
        ]
        collection = _make_mock_collection(ids, None, metadatas)
        edges = compute_heading_edges(collection)
        assert edges == []


# ── Document community detection tests ───────────────────────────────────


class TestDetectDocumentCommunities:
    """Tests for document community detection."""

    def test_empty_graph(self) -> None:
        """Empty graph produces no communities."""
        graph = nx.Graph()
        communities = detect_document_communities(graph)
        assert communities == []

    def test_single_chunk(self) -> None:
        """Single chunk produces one community."""
        graph = nx.Graph()
        graph.add_node("chunk1", category="security")
        communities = detect_document_communities(graph)
        assert len(communities) == 1
        assert "chunk1" in communities[0].chunks

    def test_small_graph_single_community(self) -> None:
        """Graph with <5 nodes returns single community."""
        graph = nx.Graph()
        for i in range(3):
            graph.add_node(f"chunk{i}", category="api")
        communities = detect_document_communities(graph)
        assert len(communities) == 1
        assert len(communities[0].chunks) == 3

    def test_larger_graph(self) -> None:
        """Larger graph with clear clusters produces communities."""
        graph = nx.Graph()
        for i in range(10):
            graph.add_node(f"chunk{i}", category="api" if i < 5 else "security")
        # Connect within clusters.
        for i in range(4):
            graph.add_edge(f"chunk{i}", f"chunk{i + 1}")
        for i in range(5, 9):
            graph.add_edge(f"chunk{i}", f"chunk{i + 1}")
        communities = detect_document_communities(graph)
        assert len(communities) >= 1
        total = sum(len(c.chunks) for c in communities)
        assert total == 10


# ── Cross-link tests ─────────────────────────────────────────────────────


class TestComputeCrossLinks:
    """Tests for cross-link detection between code and document graphs."""

    def test_filename_match(self) -> None:
        """Filename matching with ≥2 path segments creates cross-links."""
        code_graph = nx.DiGraph()
        code_graph.add_node("src/auth/login.ts", exports=[], classes=[], functions=[])

        doc_graph = nx.Graph()
        doc_graph.add_node("doc1", file_path="docs/src/auth/login.md", category="", keywords=[])

        links = compute_cross_links(code_graph, doc_graph)
        # "src/auth/login.ts" and "docs/src/auth/login.md" — basename "login" matches.
        assert any(l.relation == "filename_match" for l in links)

    def test_symbol_match(self) -> None:
        """Symbol matching creates cross-links."""
        code_graph = nx.DiGraph()
        code_graph.add_node("src/user_service.ts", exports=["UserService"], classes=[], functions=[])

        doc_graph = nx.Graph()
        doc_graph.add_node("doc1", file_path="docs/UserService.md", category="", keywords=[])

        links = compute_cross_links(code_graph, doc_graph)
        assert any(l.relation == "symbol_match" for l in links)

    def test_generic_name_no_false_positive(self) -> None:
        """Generic single-segment names don't create false positive cross-links."""
        code_graph = nx.DiGraph()
        code_graph.add_node("config.ts", exports=[], classes=[], functions=[])

        doc_graph = nx.Graph()
        doc_graph.add_node("doc1", file_path="config.md", category="", keywords=[])

        links = compute_cross_links(code_graph, doc_graph)
        # "config.ts" has only 1 path segment — should not match.
        filename_links = [l for l in links if l.relation == "filename_match"]
        assert len(filename_links) == 0

    def test_empty_graphs(self) -> None:
        """Empty graphs produce no cross-links."""
        code_graph = nx.DiGraph()
        doc_graph = nx.Graph()
        links = compute_cross_links(code_graph, doc_graph)
        assert links == []

    def test_keyword_overlap(self) -> None:
        """Category keyword overlap creates cross-links."""
        code_graph = nx.DiGraph()
        code_graph.add_node("auth/login.ts", exports=[], classes=[], functions=[])

        doc_graph = nx.Graph()
        doc_graph.add_node("doc1", file_path="docs/security.md", category="auth", keywords=["auth"])

        links = compute_cross_links(code_graph, doc_graph)
        overlap_links = [l for l in links if l.relation == "keyword_overlap"]
        assert len(overlap_links) > 0


# ── Build document graph integration test ────────────────────────────────


class TestBuildDocumentGraph:
    """Tests for the full document graph construction."""

    def test_none_collection(self) -> None:
        """None collection produces empty graph."""
        graph = build_document_graph(None)
        assert graph.number_of_nodes() == 0

    def test_graph_has_nodes(self) -> None:
        """Graph contains nodes for document chunks."""
        ids = ["chunk1", "chunk2"]
        embeddings = [[1.0, 0.0], [0.99, 0.01]]
        metadatas = [
            {"content_type": "document/markdown", "category": "api"},
            {"content_type": "document/markdown", "category": "api"},
        ]
        collection = _make_mock_collection(ids, embeddings, metadatas)
        graph = build_document_graph(collection)
        assert graph.number_of_nodes() == 2
