"""Dense vector search over ChromaDB.

Query embedding with LRU cache, distance-to-score conversion, and the
dense query path.  Extracted from the original ``retrieval.py`` monolith
as part of Phase 1.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from llama_index.core import Settings

logger = logging.getLogger(__name__)

# ── Query embedding cache ──────────────────────────────────────────────
# Process-local LRU cache so repeated identical queries (common in
# agentic loops) do not re-hit Ollama for the embedding step.  The cache
# is keyed by ``(query, embed_model_name)`` so a model swap (e.g. via
# ``Settings.embed_model = ...`` in tests) automatically invalidates
# entries from the previous model.  See ADR-016 / OpenSpec change
# ``rag-retrieval-quality-improvements`` Decision 4.
_QUERY_EMBED_CACHE_MAXSIZE = 128


@functools.lru_cache(maxsize=_QUERY_EMBED_CACHE_MAXSIZE)
def _cached_query_embedding(
    query: str,
    embed_model_name: str,
) -> tuple[float, ...]:
    """Return the query embedding, cached by ``(query, embed_model_name)``.

    The result is a tuple so it is hashable and immutable; callers
    convert to a list before passing to ChromaDB.

    Args:
        query: The user's search query string.
        embed_model_name: The current ``Settings.embed_model.model_name``,
            included in the key so that swapping models invalidates the
            cache automatically.

    Returns:
        The embedding vector as a tuple of floats.
    """
    vec = Settings.embed_model.get_query_embedding(query)
    return tuple(vec)


def _embed_query(query: str) -> list[float]:
    """Embed a query, using the LRU cache when available.

    Falls back gracefully to a direct embed call if the configured
    embed model does not expose ``model_name`` (rare; e.g. some test
    mocks).  Returns a fresh list so callers may safely mutate it.

    Args:
        query: The user's search query string.

    Returns:
        Embedding vector as a list of floats.
    """
    embed_model = Settings.embed_model
    model_name = getattr(embed_model, "model_name", None)
    if model_name is None:
        # Uncacheable model — bypass the cache rather than risk
        # collisions across instances.
        return list(embed_model.get_query_embedding(query))
    return list(_cached_query_embedding(query, model_name))


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


def _result_source(meta: dict) -> str:
    return meta.get("file_path") or meta.get("file_name") or "unknown"


def _dense_query_rows(
    store: Any,
    collection_name: str,
    query: str,
    fetch_k: int,
    metadata_filter: dict | None = None,
) -> list[dict]:
    """Query the vector store for dense matches and return result rows.

    Args:
        store: A :class:`VectorStore` instance.
        collection_name: Name of the collection to query.
        query: Free-text search query.
        fetch_k: Number of candidates to fetch.
        metadata_filter: Optional store ``where`` clause.

    Returns:
        List of result dicts with keys ``id``, ``score``, ``source``,
        ``page_label``, ``text``, ``metadata``, ``reranked``.
    """
    raw_rows = store.query_dense(
        collection_name=collection_name,
        query_embedding=_embed_query(query),
        n_results=fetch_k,
        where=metadata_filter,
    )

    rows: list[dict] = []
    for row in raw_rows:
        meta = row.get("metadata", {})
        rows.append({
            "id": row.get("id", ""),
            "score": _distance_to_score(row.get("distance")),
            "source": _result_source(meta),
            "page_label": meta.get("page_label"),
            "text": row.get("document", ""),
            "metadata": dict(meta),
            "reranked": False,
        })
    return rows
