"""Document graph construction from embedding similarity and metadata.

Computes pairwise cosine similarity between document chunk embeddings,
builds metadata-based and heading-hierarchy edges, and detects document
communities using Louvain. Also computes cross-links between code and
document communities.

All settings are read from ``config.py``. No cross-imports with ``retrieval.py``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from ...config import settings

logger = logging.getLogger(__name__)


@dataclass
class Edge:
    """A weighted edge in the document graph.

    Attributes:
        source: Source node ID (chunk ID or file path).
        target: Target node ID.
        relation: Edge relation type ("similar", "category", "keyword", "heading_child").
        weight: Edge weight (similarity score or fixed weight).
        shared_keywords: Shared keywords (for keyword edges).
    """

    source: str
    target: str
    relation: str
    weight: float = 1.0
    shared_keywords: list[str] = field(default_factory=list)


@dataclass
class DocCommunity:
    """A community of related document chunks.

    Attributes:
        label: Human-readable label (representative category).
        chunks: List of chunk IDs in the community.
        category: Representative category for this community.
    """

    label: str
    chunks: list[str]
    category: str = ""


@dataclass
class CrossLink:
    """A cross-link between a code file and a document chunk.

    Attributes:
        code: Code file path.
        doc: Document chunk ID or file path.
        relation: Relation type ("filename_match", "symbol_match", "keyword_overlap").
    """

    code: str
    doc: str
    relation: str


# ── Similarity edges ─────────────────────────────────────────────────────


def compute_similarity_edges(
    collection,
    threshold: float | None = None,
) -> list[Edge]:
    """Compute pairwise cosine similarity edges between document chunks.

    Fetches embeddings from ChromaDB, computes pairwise cosine similarity,
    and creates edges for pairs above the threshold. Only document-type
    chunks are compared (not code chunks).

    Args:
        collection: ChromaDB collection object.
        threshold: Minimum cosine similarity to create an edge.

    Returns:
        List of ``Edge`` objects with ``relation="similar"``.
    """
    if collection is None:
        return []

    if threshold is None:
        threshold = settings.doc_similarity_threshold

    # Fetch all embeddings and metadata from ChromaDB.
    try:
        result = collection.get(include=["embeddings", "metadatas"])
    except Exception as exc:
        logger.warning("Failed to fetch embeddings from ChromaDB: %s", exc)
        return []

    ids = result.get("ids", [])
    embeddings = result.get("embeddings", [])
    metadatas = result.get("metadatas", [])

    if not ids or len(embeddings) == 0:
        return []

    # Filter to document-type chunks only (skip code chunks).
    doc_indices = [
        i for i, meta in enumerate(metadatas)
        if meta and meta.get("content_type", "").startswith("document")
    ]

    if len(doc_indices) < 2:
        return []

    import numpy as np

    # Build embedding matrix for document chunks.
    doc_embeddings = np.array([embeddings[i] for i in doc_indices])
    doc_ids = [ids[i] for i in doc_indices]

    # Normalise embeddings for cosine similarity.
    norms = np.linalg.norm(doc_embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Avoid division by zero.
    normalised = doc_embeddings / norms

    # Compute pairwise cosine similarity.
    sim_matrix = normalised @ normalised.T

    edges: list[Edge] = []
    for i in range(len(doc_indices)):
        for j in range(i + 1, len(doc_indices)):
            sim = float(sim_matrix[i, j])
            if sim >= threshold:
                edges.append(Edge(
                    source=doc_ids[i],
                    target=doc_ids[j],
                    relation="similar",
                    weight=sim,
                ))

    logger.debug(
        "Computed %d similarity edges from %d document chunks (threshold=%.2f)",
        len(edges), len(doc_indices), threshold,
    )
    return edges


# ── Metadata edges ───────────────────────────────────────────────────────


def _category_edges(doc_entries: list[tuple[str, dict]]) -> list[Edge]:
    """Build edges between chunks sharing the same category."""
    edges: list[Edge] = []
    for i in range(len(doc_entries)):
        for j in range(i + 1, len(doc_entries)):
            cat_i = doc_entries[i][1].get("category")
            cat_j = doc_entries[j][1].get("category")
            if cat_i and cat_j and cat_i == cat_j:
                edges.append(Edge(
                    source=doc_entries[i][0],
                    target=doc_entries[j][0],
                    relation="category",
                    weight=1.0,
                ))
    return edges


def _keyword_edges(doc_entries: list[tuple[str, dict]]) -> list[Edge]:
    """Build edges between chunks sharing keywords."""
    edges: list[Edge] = []
    for i in range(len(doc_entries)):
        for j in range(i + 1, len(doc_entries)):
            kw_i = set(doc_entries[i][1].get("keywords", []))
            kw_j = set(doc_entries[j][1].get("keywords", []))
            shared = kw_i & kw_j
            if shared:
                edges.append(Edge(
                    source=doc_entries[i][0],
                    target=doc_entries[j][0],
                    relation="keyword",
                    weight=0.5,
                    shared_keywords=list(shared),
                ))
    return edges


def compute_metadata_edges(collection) -> list[Edge]:
    """Build edges between chunks sharing metadata categories or keywords.

    Shared category edges have weight 1.0. Shared keyword edges have
    weight 0.5 and include the shared keywords.

    Args:
        collection: ChromaDB collection object.

    Returns:
        List of ``Edge`` objects with ``relation="category"`` or ``relation="keyword"``.
    """
    if collection is None:
        return []

    try:
        result = collection.get(include=["metadatas"])
    except Exception as exc:
        logger.warning("Failed to fetch metadata from ChromaDB: %s", exc)
        return []

    ids = result.get("ids", [])
    metadatas = result.get("metadatas", [])

    if not ids:
        return []

    # Filter to document-type chunks.
    doc_entries = [
        (ids[i], metadatas[i])
        for i in range(len(ids))
        if metadatas[i] and metadatas[i].get("content_type", "").startswith("document")
    ]

    return _category_edges(doc_entries) + _keyword_edges(doc_entries)


# ── Heading hierarchy edges ──────────────────────────────────────────────


def _heading_prefix_edges(doc_chunks: list[tuple[str, str | None]]) -> list[Edge]:
    """Build parent-child edges from header path prefix matching."""
    edges: list[Edge] = []
    for chunk_id, header_path in doc_chunks:
        if not header_path:
            continue
        for other_id, other_path in doc_chunks:
            if chunk_id == other_id or not other_path:
                continue
            if other_path.startswith(header_path + "/"):
                edges.append(Edge(
                    source=chunk_id,
                    target=other_id,
                    relation="heading_child",
                    weight=1.0,
                ))
    return edges


def compute_heading_edges(collection) -> list[Edge]:
    """Build parent-child edges from markdown heading hierarchy.

    Uses the ``header_path`` metadata field (set by the ingestion pipeline)
    to determine parent-child relationships between chunks.

    Args:
        collection: ChromaDB collection object.

    Returns:
        List of ``Edge`` objects with ``relation="heading_child"``.
    """
    if collection is None:
        return []

    try:
        result = collection.get(include=["metadatas"])
    except Exception as exc:
        logger.warning("Failed to fetch metadata for heading edges: %s", exc)
        return []

    ids = result.get("ids", [])
    metadatas = result.get("metadatas", [])

    if not ids:
        return []

    # Build a map of header_path → chunk ID for document chunks.
    path_to_chunks: dict[str, list[str]] = {}
    doc_chunks: list[tuple[str, str | None]] = []

    for i in range(len(ids)):
        meta = metadatas[i] if i < len(metadatas) else None
        if not meta or not meta.get("content_type", "").startswith("document"):
            continue
        header_path = meta.get("header_path") or meta.get("heading_path")
        doc_chunks.append((ids[i], header_path))
        if header_path:
            path_to_chunks.setdefault(header_path, []).append(ids[i])

    return _heading_prefix_edges(doc_chunks)


# ── Document graph construction ──────────────────────────────────────────


def _add_doc_nodes(graph: nx.Graph, collection) -> None:
    """Add document chunk nodes from ChromaDB collection to graph."""
    try:
        result = collection.get(include=["metadatas"])
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        for i, chunk_id in enumerate(ids):
            meta = metadatas[i] if i < len(metadatas) else {}
            if meta and meta.get("content_type", "").startswith("document"):
                graph.add_node(
                    chunk_id,
                    category=meta.get("category", ""),
                    keywords=meta.get("keywords", []),
                    file_path=meta.get("file_path", ""),
                    header_path=meta.get("header_path", ""),
                )
    except Exception as exc:
        logger.warning("Failed to fetch nodes from ChromaDB: %s", exc)


def _add_edges_safe(graph: nx.Graph, edges: list[Edge]) -> None:
    """Add edges to graph only if both endpoints exist as nodes."""
    for edge in edges:
        if graph.has_node(edge.source) and graph.has_node(edge.target):
            attrs: dict = {"relation": edge.relation, "weight": edge.weight}
            if edge.shared_keywords:
                attrs["shared_keywords"] = edge.shared_keywords
            graph.add_edge(edge.source, edge.target, **attrs)


def build_document_graph(
    collection,
    threshold: float | None = None,
) -> nx.Graph:
    """Build an undirected document graph from all edge types.

    Combines similarity edges, metadata edges, and heading hierarchy edges
    into a single ``networkx.Graph``.

    Args:
        collection: ChromaDB collection object, or None if no documents indexed.
        threshold: Cosine similarity threshold for similarity edges.

    Returns:
        A ``networkx.Graph`` with document chunk nodes and relationship edges.
    """
    graph = nx.Graph()

    if collection is None:
        return graph

    if threshold is None:
        threshold = settings.doc_similarity_threshold

    _add_doc_nodes(graph, collection)
    if graph.number_of_nodes() == 0:
        return graph

    _add_edges_safe(graph, compute_similarity_edges(collection, threshold))
    _add_edges_safe(graph, compute_metadata_edges(collection))
    _add_edges_safe(graph, compute_heading_edges(collection))

    logger.debug(
        "Document graph: %d nodes, %d edges",
        graph.number_of_nodes(), graph.number_of_edges(),
    )
    return graph


# ── Document community detection ─────────────────────────────────────────


def detect_document_communities(graph: nx.Graph) -> list[DocCommunity]:
    """Detect document communities using Louvain.

    Partitions the document graph into topic clusters. Each community is
    labelled with its representative category.

    Args:
        graph: The document graph as a ``networkx.Graph``.

    Returns:
        List of ``DocCommunity`` objects with labels, chunks, and categories.
    """
    if graph.number_of_nodes() == 0:
        return []

    if graph.number_of_nodes() < 5:
        # Small graph: single community.
        chunks = list(graph.nodes())
        categories = [
            graph.nodes[n].get("category", "")
            for n in chunks
            if graph.nodes[n].get("category")
        ]
        category = categories[0] if categories else ""
        return [DocCommunity(
            label=category or "all",
            chunks=chunks,
            category=category,
        )]

    try:
        communities_sets = nx.algorithms.community.louvain_communities(graph)
    except Exception as exc:
        logger.warning("Document Louvain failed: %s", exc)
        chunks = list(graph.nodes())
        return [DocCommunity(label="all", chunks=chunks)]

    communities: list[DocCommunity] = []
    for comm_set in communities_sets:
        chunks = sorted(comm_set)
        # Determine representative category.
        categories = [
            graph.nodes[n].get("category", "")
            for n in chunks
            if graph.nodes[n].get("category")
        ]
        if categories:
            # Most common category.
            from collections import Counter
            category = Counter(categories).most_common(1)[0][0]
        else:
            category = ""
        label = category or f"Topic {len(communities) + 1}"
        communities.append(DocCommunity(
            label=label,
            chunks=chunks,
            category=category,
        ))

    communities.sort(key=lambda c: len(c.chunks), reverse=True)
    return communities


# ── Cross-links between code and document communities ────────────────────


def _filename_match_links(
    code_files: list[str],
    doc_chunks: list[tuple[str, str, str]],
) -> list[CrossLink]:
    """Detect cross-links via filename matching (≥2 path segments)."""
    links: list[CrossLink] = []
    for code_file in code_files:
        code_parts = Path(code_file).parts
        if len(code_parts) < 2:
            continue
        code_basename = Path(code_file).stem
        for doc_id, doc_path, _ in doc_chunks:
            if not doc_path:
                continue
            doc_parts = Path(doc_path).parts
            if len(doc_parts) < 2:
                continue
            if code_file in doc_path or doc_path in code_file or (
                code_basename and code_basename in doc_path
            ):
                links.append(CrossLink(
                    code=code_file,
                    doc=doc_id,
                    relation="filename_match",
                ))
    return links


def _symbol_match_links(
    code_symbols: dict[str, list[str]],
    doc_chunks: list[tuple[str, str, str]],
) -> list[CrossLink]:
    """Detect cross-links via exported symbol names in document paths."""
    links: list[CrossLink] = []
    for code_file, symbols in code_symbols.items():
        for symbol in symbols:
            for doc_id, doc_path, _ in doc_chunks:
                if not doc_path:
                    continue
                if symbol and symbol in doc_path:
                    links.append(CrossLink(
                        code=code_file,
                        doc=doc_id,
                        relation="symbol_match",
                    ))
    return links


def _keyword_overlap_links(
    code_files: list[str],
    doc_graph: nx.Graph,
) -> list[CrossLink]:
    """Detect cross-links via code directory names vs doc categories/keywords."""
    code_dirs: dict[str, list[str]] = {}
    for code_file in code_files:
        parent = Path(code_file).parent.name
        if parent:
            code_dirs.setdefault(parent, []).append(code_file)

    links: list[CrossLink] = []
    for node in doc_graph.nodes():
        category = doc_graph.nodes[node].get("category", "")
        keywords = doc_graph.nodes[node].get("keywords", [])
        if not category and not keywords:
            continue
        for dir_name, files in code_dirs.items():
            if dir_name.lower() in [k.lower() for k in keywords] or \
               dir_name.lower() == category.lower():
                for code_file in files:
                    links.append(CrossLink(
                        code=code_file,
                        doc=node,
                        relation="keyword_overlap",
                    ))
    return links


def compute_cross_links(
    code_graph: nx.DiGraph,
    doc_graph: nx.Graph,
) -> list[CrossLink]:
    """Detect connections between code and document communities.

    Uses filename matching (≥2 path segments), symbol matching (exported
    class/function names in document text), and category keyword overlap.

    Args:
        code_graph: The code graph as a ``networkx.DiGraph``.
        doc_graph: The document graph as a ``networkx.Graph``.

    Returns:
        List of ``CrossLink`` objects.
    """
    if code_graph.number_of_nodes() == 0 or doc_graph.number_of_nodes() == 0:
        return []

    # Collect code file paths and exported symbols.
    code_files: list[str] = []
    code_symbols: dict[str, list[str]] = {}
    for node in code_graph.nodes():
        code_files.append(node)
        code_symbols[node] = code_graph.nodes[node].get("exports", [])

    # Collect document file paths.
    doc_chunks: list[tuple[str, str, str]] = []
    for node in doc_graph.nodes():
        file_path = doc_graph.nodes[node].get("file_path", "")
        doc_chunks.append((node, file_path, ""))

    cross_links = (
        _filename_match_links(code_files, doc_chunks)
        + _symbol_match_links(code_symbols, doc_chunks)
        + _keyword_overlap_links(code_files, doc_graph)
    )

    # Deduplicate.
    seen: set[tuple[str, str, str]] = set()
    unique_links: list[CrossLink] = []
    for link in cross_links:
        key = (link.code, link.doc, link.relation)
        if key not in seen:
            seen.add(key)
            unique_links.append(link)

    return unique_links
