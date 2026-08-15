"""Document graph construction from embedding similarity and metadata.

Computes pairwise cosine similarity between document chunk embeddings,
builds metadata-based and heading-hierarchy edges, and detects document
communities through the shared strategy registry. Also computes cross-links
between code and document communities.

Settings arrive through the frozen ``EffectiveSettings`` value object. The
module has no cross-imports with ``core/retrieval``.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import networkx as nx

from ..community import partition_graph
from ..settings import (
    EffectiveSettings,
    get_default_effective_settings,
    resolve_effective_settings,
)

logger = logging.getLogger(__name__)


class CollectionView:
    """Read-only view over one collection, backed by the VectorStore ABC.

    The document graph needs embeddings and metadata for every chunk. It used
    to receive a raw ChromaDB collection, which meant the codebase map had to
    construct a ``chromadb.PersistentClient`` directly — the one place in the
    codebase that bypassed the vector-store abstraction (ADR-034). This view
    keeps the graph code's ``.get(include=[...])`` shape while routing the
    read through ``VectorStore.fetch_all``, so ChromaDB stays confined to
    ``core/vectordb/chroma.py``.
    """

    def __init__(self, store, collection_name: str = "documents") -> None:
        self._store = store
        self._collection_name = collection_name

    def get(self, include: list[str]) -> dict[str, list]:
        payload = self._store.fetch_all(self._collection_name, include)
        return payload if payload is not None else {}

    def count(self) -> int:
        return self._store.count(self._collection_name)


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
        threshold = get_default_effective_settings().doc_similarity_threshold

    _add_doc_nodes(graph, collection)
    if graph.number_of_nodes() == 0:
        return graph

    _add_edges_safe(graph, compute_similarity_edges(collection, threshold))
    _add_edges_safe(graph, compute_metadata_edges(collection))
    _add_edges_safe(graph, compute_heading_edges(collection))

    logger.debug(
        "Document graph: %d nodes, %d edges",
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )
    return graph


# ── Document community detection ─────────────────────────────────────────


def detect_document_communities(
    graph: nx.Graph,
    settings: EffectiveSettings | None = None,
) -> list[DocCommunity]:
    """Detect document communities via the configured strategy.

    Partitions the document graph into topic clusters using the
    ``community_algorithm`` strategy resolved through the shared
    ``core/community`` registry, seeded with ``community_seed``. Each
    community is labelled with its representative category.

    Args:
        graph: The document graph as a ``networkx.Graph``.
        settings: Effective settings carrying the algorithm name and seed.
            Defaults to the composition-root instance; the codebase-map
            boundary passes its resolved instance explicitly.

    Returns:
        List of ``DocCommunity`` objects with labels, chunks, and categories.
    """
    if graph.number_of_nodes() == 0:
        return []

    effective = resolve_effective_settings(settings)

    if graph.number_of_nodes() < 5:
        # Small graph: single community.
        chunks = list(graph.nodes())
        categories = [
            graph.nodes[n].get("category", "") for n in chunks if graph.nodes[n].get("category")
        ]
        category = categories[0] if categories else ""
        return [
            DocCommunity(
                label=category or "all",
                chunks=chunks,
                category=category,
            )
        ]

    try:
        communities_sets = partition_graph(
            graph,
            algorithm=effective.community_algorithm,
            seed=effective.community_seed,
        )
    except Exception as exc:
        logger.warning(
            "Document community detection (%s) failed: %s",
            effective.community_algorithm,
            exc,
        )
        chunks = list(graph.nodes())
        return [DocCommunity(label="all", chunks=chunks)]

    communities: list[DocCommunity] = []
    for comm_set in communities_sets:
        # Document-graph node IDs are strings; the shared strategy contract
        # remains generic for consumers that use other hashable identifiers.
        chunks = sorted(cast(set[str], comm_set))
        # Determine representative category.
        categories = [
            graph.nodes[n].get("category", "") for n in chunks if graph.nodes[n].get("category")
        ]
        if categories:
            # Most common category.
            category = Counter(categories).most_common(1)[0][0]
        else:
            category = ""
        label = category or f"Topic {len(communities) + 1}"
        communities.append(
            DocCommunity(
                label=label,
                chunks=chunks,
                category=category,
            )
        )

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
            if (
                code_file in doc_path
                or doc_path in code_file
                or (code_basename and code_basename in doc_path)
            ):
                links.append(
                    CrossLink(
                        code=code_file,
                        doc=doc_id,
                        relation="filename_match",
                    )
                )
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
                    links.append(
                        CrossLink(
                            code=code_file,
                            doc=doc_id,
                            relation="symbol_match",
                        )
                    )
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
            if (
                dir_name.lower() in [k.lower() for k in keywords]
                or dir_name.lower() == category.lower()
            ):
                for code_file in files:
                    links.append(
                        CrossLink(
                            code=code_file,
                            doc=node,
                            relation="keyword_overlap",
                        )
                    )
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


# ── Re-exports ───────────────────────────────────────────────────────────
# Edge computation lives in ``similarity.py`` after the task 8.6 split.

from .similarity import (  # noqa: E402
    _add_doc_nodes,
    _add_edges_safe,
    compute_heading_edges,
    compute_metadata_edges,
    compute_similarity_edges,
)
