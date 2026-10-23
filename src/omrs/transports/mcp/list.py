"""MCP tools: list_indexed_documents and list_collections."""

from __future__ import annotations

import asyncio

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from ...core.ingestion import list_documents as _list_documents
from ...core.retrieval import list_collections as _list_collections
from .context import mcp_context
from .errors import error_message, log_tool_error

LIST_DOCUMENTS_DESCRIPTION = (
    "List all documents currently indexed in the RAG store, with source "
    "paths, chunk counts, and tri-state orphaned status. Orphaned means "
    "missing on this machine. Optionally scope to a specific collection."
)
LIST_COLLECTIONS_DESCRIPTION = (
    "List all available ChromaDB collections with their document and chunk counts."
)
ANNOTATIONS = ToolAnnotations(read_only_hint=True, destructive_hint=False)


async def list_indexed_documents(collection: str = "documents", *, ctx: Context) -> list[dict]:
    """List indexed documents and machine-local orphaned status."""
    mcp = mcp_context(ctx)
    try:
        async with mcp.admit():
            return await asyncio.to_thread(
                _list_documents, collection_name=collection, store=mcp.engine.store
            )
    except Exception as exc:
        log_tool_error(mcp, "list_indexed_documents", exc)
        return [
            {
                "status": "error",
                "message": error_message(mcp, exc),
            }
        ]


async def list_collections(*, ctx: Context) -> list[dict]:
    """List all ChromaDB collections with counts."""
    mcp = mcp_context(ctx)
    try:
        async with mcp.admit():
            return await asyncio.to_thread(_list_collections, store=mcp.engine.store)
    except Exception as exc:
        log_tool_error(mcp, "list_collections", exc)
        return [
            {
                "status": "error",
                "message": error_message(mcp, exc),
            }
        ]
