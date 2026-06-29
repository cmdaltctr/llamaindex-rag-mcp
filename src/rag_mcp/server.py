"""MCP server exposing RAG document tools over stdio.

Start with:
    uv run rag-mcp

Tools
-----
- ingest_documents       – index a file / directory into the RAG store
- search_documents       – semantic search over the indexed documents
- list_indexed_documents – show what's currently in the store
- list_collections       – list all ChromaDB collections with counts
- delete_documents       – remove documents by path, metadata filter, or drop collection
"""

import asyncio
import logging

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .config import HYBRID_ENABLED, SIMILARITY_THRESHOLD, TOP_K
from .ingestion import ingest_path_async, list_documents as _list_documents
from .retrieval import search

logger = logging.getLogger(__name__)

# Load .env from the working directory (project root when run via `uv run`)
load_dotenv()

mcp = FastMCP("rag-mcp", log_level="WARNING")


# ── Tool 1: Ingest ----------------------------------------------------------

@mcp.tool(
    description=(
        "Index one or more documents or a directory into the RAG store. "
        "Accepts a file path or directory path. Optionally specify a "
        "target ChromaDB collection. Supported formats: PDF, "
        "DOCX, PPTX, TXT, Markdown, HTML, CSV."
    ),
    annotations=ToolAnnotations(destructiveHint=True),
)
async def ingest_documents(path: str, collection: str = "documents") -> dict:
    """Index documents into the RAG vector store."""
    return await ingest_path_async(path, collection_name=collection)


# ── Tool 2: Search ----------------------------------------------------------

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
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def search_documents(
    query: str,
    top_k: int = TOP_K,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    rerank: bool | None = None,
    hybrid: bool = HYBRID_ENABLED,
    collection: str = "documents",
    metadata_filter: dict | None = None,
) -> list[dict]:
    """Search indexed documents for semantically relevant chunks.

    Args:
        query: Natural language search query.
        top_k: Maximum number of chunks to return (default from config).
        similarity_threshold: Minimum relevance score to include a
            result. 0.0 means no filtering (default).
        rerank: Tri-state rerank control:
            - ``True``: force reranking (explicit opt-in)
            - ``False``: force no reranking (explicit opt-out)
            - ``None``: apply policy resolver (default)
            The policy resolver checks ``RERANK_ENABLED``, then
            ``RERANK_ENABLED_FOR_SEMANTIC`` and ``HARD_TECHNICAL_THRESHOLD``
            to decide whether to enable reranking based on query type.
        hybrid: If True, fuse dense vector retrieval with sparse keyword
            retrieval via Reciprocal Rank Fusion before reranking.
        collection: Name of the ChromaDB collection to search
            (default "documents").
        metadata_filter: Optional ChromaDB-compatible ``where`` clause
            (e.g. ``{"category": "ai"}``) restricting results to chunks
            whose metadata matches.  When omitted, the unfiltered
            retrieval path is used.

    Returns:
        On success, a list of result dicts (`score`, `source`,
        `page_label`, `text`, `reranked`).  On failure, a single-element
        list ``[{"status": "error", "error_type": <category>, "message": ...}]``
        where ``error_type`` is one of ``"validation"``, ``"retrieval"``,
        or ``"internal"``.  The handler never raises.
    """
    try:
        return await asyncio.to_thread(
            search,
            query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            rerank=rerank,
            hybrid=hybrid,
            collection_name=collection,
            metadata_filter=metadata_filter,
        )
    except ValueError as exc:
        # ChromaDB raises ValueError for malformed ``where`` clauses
        # (unsupported operator, type mismatch, etc.).  Treat any
        # ValueError as a client-side input problem.
        logger.warning("search_documents validation error: %s", exc)
        return [{
            "status": "error",
            "error_type": "validation",
            "message": str(exc),
        }]
    except Exception as exc:
        # ChromaDB query / vector store failures end up here.  Distinguish
        # genuinely unexpected errors (``internal``) from the common
        # ChromaDB / vector-store failure mode (``retrieval``).  Any
        # exception originating from the chromadb namespace, or any
        # exception while a metadata filter was attached, is treated as
        # ``retrieval``; everything else is ``internal``.
        is_chroma = (
            type(exc).__module__.startswith("chromadb")
            or "chroma" in type(exc).__name__.lower()
        )
        if is_chroma or metadata_filter is not None:
            error_type = "retrieval"
        else:
            error_type = "internal"
        logger.warning(
            "search_documents %s error: %s: %s",
            error_type, type(exc).__name__, exc,
        )
        return [{
            "status": "error",
            "error_type": error_type,
            "message": f"{type(exc).__name__}: {exc}",
        }]


# ── Tool 3: List indexed documents ------------------------------------------

@mcp.tool(
    description=(
        "List all documents currently indexed in the RAG store, "
        "with their source paths and chunk counts. Optionally "
        "scope to a specific ChromaDB collection."
    ),
    annotations=ToolAnnotations(readOnlyHint=True),
)
def list_indexed_documents(collection: str = "documents") -> list[dict]:
    """List all documents that have been indexed so far."""
    return _list_documents(collection_name=collection)


# ── Tool 4: List collections -------------------------------------------------

@mcp.tool(
    description=(
        "List all available ChromaDB collections with their document "
        "and chunk counts."
    ),
    annotations=ToolAnnotations(readOnlyHint=True),
)
def list_collections() -> list[dict]:
    """List all ChromaDB collections with counts."""
    from .retrieval import list_collections as _list_collections

    return _list_collections()


# ── Tool 5: Delete documents -------------------------------------------------


@mcp.tool(
    description=(
        "Remove documents from the RAG store. Accepts an optional "
        "path (delete chunks for a specific file), metadata_filter "
        "(delete chunks matching a metadata filter as a JSON object), "
        "or collection (delete an entire collection — when provided "
        "without path or metadata_filter, the collection itself is "
        "dropped). Use dry_run=true to preview without modifying data."
    ),
    annotations=ToolAnnotations(destructiveHint=True),
)
def delete_documents(
    path: str | None = None,
    metadata_filter: dict | None = None,
    collection: str = "documents",
    dry_run: bool = False,
) -> dict:
    """Remove documents from the RAG vector store.

    Args:
        path: Source file path whose chunks to delete. When omitted and
            no ``metadata_filter`` is given, the collection itself is
            dropped.
        metadata_filter: ChromaDB ``where`` clause as a dict
            (e.g. ``{"category": "uncategorised"}``). Must be a non-empty
            dict.
        collection: Name of the ChromaDB collection to operate on
            (default ``"documents"``).
        dry_run: If True, preview what would be deleted without
            modifying ChromaDB (default False).

    Returns:
        A dict summarising the operation: ``status``, ``mode``,
        ``collection``, and relevant counts.
    """
    from .ingestion import (
        preview_delete,
        remove_document,
        remove_by_metadata,
        remove_collection,
    )

    # Determine operation mode
    if path is not None:
        # Mode: delete by file path
        if dry_run:
            return preview_delete(path=str(path), collection_name=collection)
        result = remove_document(str(path), collection_name=collection)
        result["mode"] = "path"
        return result

    if metadata_filter is not None:
        # Mode: delete by metadata filter
        if not metadata_filter:
            return {
                "status": "error",
                "message": "metadata_filter must be a non-empty dict.",
            }

        if dry_run:
            return preview_delete(
                metadata_filter=metadata_filter,
                collection_name=collection,
            )
        result = remove_by_metadata(
            metadata_filter, collection_name=collection
        )
        result["mode"] = "metadata"
        return result

    # Mode: delete by collection (drop) — no path or metadata_filter given
    if dry_run:
        return preview_delete(collection_name=collection)
    result = remove_collection(collection)
    result["mode"] = "collection"
    return result


# ── Tool 6: Codebase map ----------------------------------------------------

@mcp.tool(
    description=(
        "Generate a compact codebase map showing file types, code communities, "
        "document communities, cross-links, and architectural hubs. Useful for "
        "agents starting a session on an unfamiliar codebase. Results are cached "
        "per-project keyed by git commit hash. Use refresh=true to force rebuild."
    ),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def get_codebase_map(path: str = ".", refresh: bool = False) -> str:
    """Generate a compact codebase map for the given project path.

    Args:
        path: Project directory path (default current directory).
        refresh: If True, rebuild the map regardless of cache state.

    Returns:
        Formatted codebase map text string. On error, returns a JSON string
        with ``{"status": "error", "message": "..."}``.
    """
    from .codebase_map import get_codebase_map_text

    return get_codebase_map_text(path=path, refresh=refresh)


def main() -> None:
    """Start the MCP server on stdio transport."""
    import logging
    import sys

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
