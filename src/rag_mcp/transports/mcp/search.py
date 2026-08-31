"""MCP tool: search_documents."""

from __future__ import annotations

import asyncio

from mcp.types import ToolAnnotations

from ...core.retrieval import search
from . import (
    _error_detail,
    _error_message,
    _get_profile_resolver,
    _get_reranker,
    _log_tool_error,
    mcp,
)


@mcp.tool(
    description=(
        "Search the indexed documents using semantic similarity. "
        "Returns the most relevant text chunks with their source file "
        "and relevance score. Optionally re-score results with a "
        "cross-encoder reranker for better precision, or filter by "
        "a minimum similarity threshold. Accepts an optional "
        "collection name to scope the search and an optional "
        "metadata_filter to restrict results by metadata fields."
    ),
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
)
async def search_documents(
    query: str,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    rerank: bool | None = None,
    hybrid: bool | None = None,
    diagnostics: bool = False,
    collection: str = "documents",
    metadata_filter: dict | None = None,
) -> list[dict]:
    """Search indexed documents for semantically relevant chunks.

    Args:
        query: Natural language search query.
        top_k: Maximum number of chunks to return. When None, the
            selected collection profile supplies the default.
        similarity_threshold: Minimum canonical dense similarity to include
            without reranking. In hybrid/no-rerank mode it constrains dense
            evidence before RRF; successful reranking uses the calibrated
            reranker threshold transform. When None, the collection profile
            supplies the default.
        rerank: Tri-state rerank control:
            - ``True``: force reranking (explicit opt-in)
            - ``False``: force no reranking (explicit opt-out)
            - ``None``: apply policy resolver (default)
        hybrid: Fuse dense vector retrieval with sparse keyword retrieval
            via Reciprocal Rank Fusion. When None, the collection profile
            supplies the default.
        diagnostics: Include core-produced retrieval diagnostics when true.
        collection: Name of the ChromaDB collection to search.
        metadata_filter: ChromaDB-compatible filter for dense and sparse candidates.

    Returns:
        On success, a list of result dicts. On failure, a single-element
        list with an error dict. The handler never raises.
    """
    try:
        try:
            effective = _get_profile_resolver().resolve(collection)
        except ValueError as exc:
            return [
                {
                    "status": "error",
                    "error_type": "validation",
                    "message": _error_detail(exc),
                }
            ]

        if top_k is None:
            top_k = effective.top_k
        if similarity_threshold is None:
            similarity_threshold = effective.retrieval.similarity_threshold
        if hybrid is None:
            hybrid = effective.hybrid_enabled
        return await asyncio.to_thread(
            search,
            query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            rerank=rerank,
            hybrid=hybrid,
            collection_name=collection,
            metadata_filter=metadata_filter,
            include_diagnostics=diagnostics,
            reranker=_get_reranker(),
            effective_settings=effective,
        )
    except ValueError as exc:
        _log_tool_error("search_documents validation", exc)
        return [
            {
                "status": "error",
                "error_type": "validation",
                "message": _error_detail(exc),
            }
        ]
    except Exception as exc:
        is_chroma = (
            type(exc).__module__.startswith("chromadb") or "chroma" in type(exc).__name__.lower()
        )
        if is_chroma or metadata_filter is not None:
            error_type = "retrieval"
        else:
            error_type = "internal"
        _log_tool_error(f"search_documents {error_type}", exc)
        return [
            {
                "status": "error",
                "error_type": error_type,
                "message": _error_message(exc),
            }
        ]
