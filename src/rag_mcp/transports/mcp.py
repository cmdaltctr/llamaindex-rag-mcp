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
- get_codebase_map       – generate a compact codebase map
- change_collection_profile – change the profile bound to a collection

This module is the MCP transport. It validates input, delegates to
``core/``, and formats output. No business logic lives here.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..config import get_settings
from ..core.ingestion import ingest_path_async, list_documents as _list_documents
from ..core.profiles import ProfileResolver
from ..core.retrieval import search

# Import the composition root early so the LlamaIndex global
# ``Settings.embed_model`` is assigned before any retrieval call
# (previously done at import time in ``config.py``; see ADR-031).
# The composition root also owns construction of the reranker (spec:
# all provider/pipeline instantiation happens in ``compose.py``).
from .. import compose  # noqa: F401

logger = logging.getLogger(__name__)

# Load .env from the working directory (project root when run via `uv run`)
load_dotenv()

# Pre-constructed reranker wired by the composition root.  Construction is
# cheap (the ONNX session loads lazily on first rerank), and the process-wide
# model cache preserves load-once semantics regardless of instance count.
_reranker = compose.build_reranker()

# Phase 4: profile resolver for per-collection profile resolution.
# Reads collection metadata tags through the vector store interface.
_profile_resolver = compose.build_profile_resolver()


# ── FastMCP lifespan (forward-compatibility slot) ──────────────────────────
# The lifespan is passed as ``None`` today. The structural slot is preserved
# so that pre-loading expensive resources (reranker ONNX model, embedding
# client, vector store connection) can be added without restructuring the
# module. See PROPOSAL §5.2 (transports/mcp.py compatibility note).

@asynccontextmanager
async def _noop_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Yield an empty context — no pre-loaded resources today.

    Replacing this with a real lifespan (e.g. one that constructs the
    pipeline via ``compose.build_pipeline()``) requires no structural
    change to this module.
    """
    yield {}


mcp = FastMCP("rag-mcp", log_level="WARNING", lifespan=_noop_lifespan)


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
    """Index documents into the RAG vector store.

    Returns an error dict on any failure (gotcha #1 — never raise from
    MCP tool handlers).
    """
    try:
        effective = _profile_resolver.resolve(collection)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    try:
        return await ingest_path_async(
            path, collection_name=collection, effective_settings=effective
        )
    except Exception as exc:
        logger.warning("ingest_documents error: %s: %s", type(exc).__name__, exc)
        return {
            "status": "error",
            "message": f"{type(exc).__name__}: {exc}",
        }


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
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    rerank: bool | None = None,
    hybrid: bool | None = None,
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
        hybrid: If True, fuse dense vector retrieval with sparse keyword
            retrieval via Reciprocal Rank Fusion before reranking.
        collection: Name of the ChromaDB collection to search.
        metadata_filter: Optional ChromaDB-compatible ``where`` clause.

    Returns:
        On success, a list of result dicts. On failure, a single-element
        list with an error dict. The handler never raises.
    """
    try:
        try:
            effective = _profile_resolver.resolve(collection)
        except ValueError as exc:
            return [{
                "status": "error",
                "error_type": "validation",
                "message": str(exc),
            }]

        if top_k is None and effective is not None:
            top_k = effective.top_k
        if similarity_threshold is None:
            similarity_threshold = get_settings().retrieval.similarity_threshold
        if hybrid is None and effective is not None:
            hybrid = effective.hybrid_enabled
        elif hybrid is None:
            hybrid = get_settings().retrieval.hybrid_enabled
        return await asyncio.to_thread(
            search,
            query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            rerank=rerank,
            hybrid=hybrid,
            collection_name=collection,
            metadata_filter=metadata_filter,
            reranker=_reranker,
            effective_settings=effective,
        )
    except ValueError as exc:
        logger.warning("search_documents validation error: %s", exc)
        return [{
            "status": "error",
            "error_type": "validation",
            "message": str(exc),
        }]
    except Exception as exc:
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
    try:
        return _list_documents(collection_name=collection)
    except Exception as exc:
        logger.warning("list_indexed_documents error: %s: %s", type(exc).__name__, exc)
        return [{
            "status": "error",
            "message": f"{type(exc).__name__}: {exc}",
        }]


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
    from ..core.retrieval import list_collections as _list_collections

    try:
        return _list_collections()
    except Exception as exc:
        logger.warning("list_collections error: %s: %s", type(exc).__name__, exc)
        return [{
            "status": "error",
            "message": f"{type(exc).__name__}: {exc}",
        }]


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

    Returns an error dict on any failure (gotcha #1).
    """
    from ..core.ingestion import (
        preview_delete,
        remove_document,
        remove_by_metadata,
        remove_collection,
    )

    try:
        if path is not None:
            if dry_run:
                return preview_delete(path=str(path), collection_name=collection)
            result = remove_document(str(path), collection_name=collection)
            result["mode"] = "path"
            return result

        if metadata_filter is not None:
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

        if dry_run:
            return preview_delete(collection_name=collection)
        result = remove_collection(collection)
        result["mode"] = "collection"
        return result
    except Exception as exc:
        logger.warning("delete_documents error: %s: %s", type(exc).__name__, exc)
        return {
            "status": "error",
            "message": f"{type(exc).__name__}: {exc}",
        }


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

    Returns a JSON error string on failure (gotcha #1).
    """
    import json

    try:
        from ..core.codebase.codebase_map import get_codebase_map_text

        return get_codebase_map_text(path=path, refresh=refresh)
    except Exception as exc:
        logger.warning("get_codebase_map error: %s: %s", type(exc).__name__, exc)
        return json.dumps({
            "status": "error",
            "message": f"{type(exc).__name__}: {exc}",
        })


# ── Tool 7: Change collection profile (Phase 4) ─────────────────────


@mcp.tool(
    description=(
        "Change the profile bound to a ChromaDB collection. Profiles "
        "control retrieval behaviour: 'documents' (quality-first, reranker "
        "on, dense-only) or 'codebase' (speed-first, reranker off, hybrid). "
        "The change is non-destructive — existing chunks are NOT re-chunked "
        "or re-embedded. Query-time levers apply immediately; ingest-time "
        "levers apply to future ingests only. Returns a preview on first "
        "call; pass confirm=true to apply."
    ),
    annotations=ToolAnnotations(destructiveHint=True),
)
def change_collection_profile(
    collection: str,
    profile: str,
    confirm: bool = False,
) -> dict:
    """Change the profile bound to a collection.

    Returns an error dict on any failure (gotcha #1).
    """
    from ..core.profiles import apply_profile_change, generate_safety_contract

    if profile not in ("documents", "codebase"):
        return {
            "status": "error",
            "message": (
                f"Invalid profile {profile!r}. Available: documents, codebase."
            ),
        }

    if not confirm:
        try:
            contract = generate_safety_contract(
                collection, profile, resolver=_profile_resolver
            )
        except Exception as exc:
            return {"status": "error", "message": str(exc)}
        return {
            "status": "preview",
            "contract": contract,
            "confirm_required": True,
        }

    try:
        return apply_profile_change(collection, profile)
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def main() -> None:
    """Start the MCP server on stdio transport."""
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
