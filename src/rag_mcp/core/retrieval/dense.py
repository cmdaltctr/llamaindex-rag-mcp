"""Store-neutral dense vector search.

Query embedding with an LRU cache and adaptation of canonical vector-store
rows into the retrieval result shape.
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


def _result_source(meta: dict) -> str:
    return meta.get("file_path") or meta.get("file_name") or "unknown"


# Stable lineage metadata read into every public result row. These are
# plain metadata keys persisted by ingestion; retrieval reads them without
# importing the ingestion layer (invariant: ingestion and retrieval share
# only settings). Values are None for rows stored without lineage, such as
# experiment precomputed rows.
LINEAGE_METADATA_KEYS = (
    "source_id",
    "source_version",
    "chunk_id",
    "source_chunk_index",
    "source_chunk_count",
)


def _lineage_fields(meta: dict) -> dict:
    """Return additive stable lineage fields read from stored metadata."""
    return {key: meta.get(key) for key in LINEAGE_METADATA_KEYS}


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
        ``page_label``, ``text``, ``metadata``, ``reranked``, plus the
        additive stable lineage fields from ``LINEAGE_METADATA_KEYS``.
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
        rows.append(
            {
                "id": row.get("id", ""),
                "score": row["score"],
                "score_kind": row["score_kind"],
                "source": _result_source(meta),
                "page_label": meta.get("page_label"),
                "text": row.get("document", ""),
                "metadata": dict(meta),
                "reranked": False,
                **_lineage_fields(meta),
            }
        )
    return rows
