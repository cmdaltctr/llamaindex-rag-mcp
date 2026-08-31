"""MCP tools: list_indexed_documents and list_collections."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from ...core.ingestion import list_documents as _list_documents
from . import _error_message, _log_tool_error, mcp


@mcp.tool(
    description=(
        "List all documents currently indexed in the RAG store, with source "
        "paths, chunk counts, and tri-state orphaned status. Orphaned means "
        "missing on this machine. Optionally scope to a specific collection."
    ),
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
)
def list_indexed_documents(collection: str = "documents") -> list[dict]:
    """List indexed documents and machine-local orphaned status."""
    try:
        return _list_documents(collection_name=collection)
    except Exception as exc:
        _log_tool_error("list_indexed_documents", exc)
        return [
            {
                "status": "error",
                "message": _error_message(exc),
            }
        ]


@mcp.tool(
    description=("List all available ChromaDB collections with their document and chunk counts."),
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
)
def list_collections() -> list[dict]:
    """List all ChromaDB collections with counts."""
    from ...core.retrieval import list_collections as _list_collections

    try:
        return _list_collections()
    except Exception as exc:
        _log_tool_error("list_collections", exc)
        return [
            {
                "status": "error",
                "message": _error_message(exc),
            }
        ]
