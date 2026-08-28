"""Edge computation for the document-similarity graph.

Split out of ``doc_graph.py`` (task 8.6), which exceeded the 500-line
ceiling. This module owns the four edge kinds — embedding similarity,
shared category, shared keywords, and heading prefixes — plus the helpers
that assemble them. ``doc_graph.py`` keeps graph assembly and community
detection.

Construction is deterministic: cosine similarity and metadata comparison
only, with no LLM involvement (AGENTS.md invariant #8).
"""

from __future__ import annotations

import logging

import networkx as nx

from ..settings import get_default_effective_settings
from .doc_graph import Edge

logger = logging.getLogger(__name__)


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
        threshold = get_default_effective_settings().doc_similarity_threshold

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


