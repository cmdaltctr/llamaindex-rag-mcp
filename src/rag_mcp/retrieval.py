"""Semantic search over the ChromaDB-backed vector index."""

from __future__ import annotations

import chromadb
from llama_index.core import Settings

from .config import CHROMA_PERSIST_DIR, RERANK_ENABLED, SIMILARITY_THRESHOLD, TOP_K
from .chroma_utils import iter_collection_metadatas
from .reranker import CrossEncoderReranker


def _effective_threshold(
    similarity_threshold: float,
    rerank: bool,
) -> float:
    """Compute the effective score threshold, accounting for reranker scores.

    Cross-encoder sigmoid scores occupy a different range than cosine
    similarity.  Valid reranker results can score as low as 0.01–0.05,
    while cosine similarity rarely goes below 0.3 for relevant matches.

    When reranking is active, the threshold is scaled down by 30× so
    that a ``similarity_threshold=0.3`` becomes 0.01 — roughly equivalent
    to "keep anything the reranker considers a match, filter clear noise".

    The 30× factor was calibrated from experiment data:
    - Strong reranker matches: 0.79–1.0
    - Weak but correct matches: 0.015 (Colosseum query)
    - Clear noise: < 0.003

    Args:
        similarity_threshold: User-supplied threshold (0.0 = no filtering).
        rerank: Whether the cross-encoder reranker is active.

    Returns:
        The effective threshold to apply to scores.
    """
    if similarity_threshold <= 0.0:
        return 0.0
    return similarity_threshold / 30 if rerank else similarity_threshold


def _distance_to_score(distance: float | None) -> float:
    """Convert a ChromaDB L2 distance to a 0–1 similarity score.

    The single canonical conversion shared by every non-reranked
    retrieval path: ``score = 1.0 / (1.0 + distance)``.  Closer distance
    yields higher score.  See ADR-015 / OpenSpec change
    ``rag-reliability-correctness-fixes`` Decision 3.

    Args:
        distance: Raw L2 distance from ChromaDB (``None`` is treated as 0).

    Returns:
        Float in ``(0, 1]``.
    """
    if distance is None:
        return 0.0
    return 1.0 / (1.0 + distance)


def search(
    query: str,
    top_k: int = TOP_K,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    rerank: bool = RERANK_ENABLED,
    collection_name: str = "documents",
    metadata_filter: dict | None = None,
) -> list[dict]:
    """Run a semantic similarity search over every indexed document.

    Args:
        query: Free-text search query.
        top_k: Maximum number of chunks to return (default from env or 5).
        similarity_threshold: Minimum score to include a result
            (0.0 = no filtering, default from env).  When ``rerank``
            is True the threshold is scaled down by 30× because
            cross-encoder sigmoid scores occupy a lower range than
            cosine similarity.  For example, 0.3 becomes 0.01.
        rerank: If True, re-score results with the cross-encoder
            reranker for better precision (default from env).
        collection_name: Name of the ChromaDB collection to search
            (default ``"documents"`` for backward compatibility).
        metadata_filter: Optional ChromaDB ``where`` clause to filter
            results by metadata fields (e.g. ``{"category": "AI"}``).
            When provided, the filter is applied server-side via
            ChromaDB's native ``where`` parameter — only matching
            chunks are returned from the vector store.

    Returns:
        A list of dicts sorted by descending relevance score, each with:
            score      – float (0–1, vector similarity or reranker score)
            source     – source file path
            page_label – page number (or None)
            text       – the chunk text
            reranked   – bool (True if cross-encoder re-scored the result)

    Raises:
        ValueError: If ``metadata_filter`` is rejected by ChromaDB
            (unsupported operator, type mismatch, etc.).  Other
            ChromaDB-side failures propagate as their original
            exception types so the MCP layer can classify them.
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    try:
        collection = db.get_collection(collection_name)
    except Exception:
        return []

    if collection.count() == 0:
        return []

    # Fetch more candidates when reranking so the cross-encoder
    # has a meaningful pool to re-score.
    fetch_k = top_k * 2 if rerank else top_k

    # Both retrieval paths (filtered and unfiltered) issue the same direct
    # ChromaDB query.  This guarantees the pre-threshold ``score`` field
    # is computed by exactly the same formula on both paths — the
    # ``1.0 / (1.0 + distance)`` conversion in ``_distance_to_score``.
    # See ADR-015 / OpenSpec change ``rag-reliability-correctness-fixes``
    # Decision 3.
    query_embedding = Settings.embed_model.get_query_embedding(query)

    query_kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": fetch_k,
        "include": ["metadatas", "documents", "distances"],
    }
    if metadata_filter:
        query_kwargs["where"] = metadata_filter

    raw = collection.query(**query_kwargs)

    results: list[dict] = []
    ids = raw.get("ids", [[]])[0]
    documents = raw.get("documents", [[]])[0]
    metadatas = raw.get("metadatas", [[]])[0]
    distances = raw.get("distances", [[]])[0]

    for i, _chunk_id in enumerate(ids):
        meta = metadatas[i] if i < len(metadatas) else {}
        text = documents[i] if i < len(documents) else ""
        distance = distances[i] if i < len(distances) else None

        results.append({
            "score": _distance_to_score(distance),
            "source": (
                meta.get("file_path")
                or meta.get("file_name")
                or "unknown"
            ),
            "page_label": meta.get("page_label"),
            "text": text,
            "reranked": False,
        })

    # Optional: re-score with cross-encoder reranker.
    if rerank and results:
        reranker = CrossEncoderReranker()
        results = reranker.rerank(query, results, top_k=top_k)
        # Propagate the reranked flag from the internal _reranked key.
        for r in results:
            r["reranked"] = r.pop("_reranked", False)

    # Filter by similarity threshold (applies after reranking).
    #
    # Reranker scores are sigmoid-normalised and occupy a different range
    # than cosine similarity.  A cosine threshold of 0.3 is a weak match,
    # but the reranker may assign a valid result only 0.015 (sigmoid).
    # Scale the threshold down by 30× when reranking to avoid over-filtering.
    effective_threshold = _effective_threshold(similarity_threshold, rerank)
    if effective_threshold > 0.0:
        results = [
            r for r in results if r["score"] >= effective_threshold
        ]

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def list_collections() -> list[dict]:
    """List all ChromaDB collections with document and chunk counts.

    Returns:
        A list of dicts, each with:
        - ``name`` — collection name
        - ``document_count`` — approximate number of unique source files
        - ``chunk_count`` — total number of chunks in the collection
    """
    db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    collections: list[dict] = []
    for coll in db.list_collections():
        try:
            chunk_count = coll.count()
            # Estimate unique documents by counting distinct file_path/file_name
            # values in metadata.
            doc_sources: set[str] = set()
            if chunk_count > 0:
                for meta in iter_collection_metadatas(coll):
                    if meta is None:
                        continue
                    source = (
                        meta.get("file_path")
                        or meta.get("file_name")
                        or "unknown"
                    )
                    doc_sources.add(source)

            collections.append({
                "name": coll.name,
                "document_count": len(doc_sources),
                "chunk_count": chunk_count,
            })
        except Exception:
            # Skip collections that can't be accessed
            continue

    return sorted(collections, key=lambda c: c["name"])
