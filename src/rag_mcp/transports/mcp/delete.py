"""MCP tool: delete_documents."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from . import _error_message, _log_tool_error, mcp


@mcp.tool(
    description=(
        "Remove documents from the RAG store. Accepts an optional "
        "path (delete chunks for a specific file), metadata_filter "
        "(delete chunks matching a metadata filter as a JSON object), "
        "or collection (delete an entire collection — when provided "
        "without path or metadata_filter, the collection itself is "
        "dropped). Use dry_run=true to preview without modifying data."
    ),
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
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
    from ...core.ingestion import (
        preview_delete,
        remove_by_metadata,
        remove_collection,
        remove_document,
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
            result = remove_by_metadata(metadata_filter, collection_name=collection)
            result["mode"] = "metadata"
            return result

        if dry_run:
            return preview_delete(collection_name=collection)
        result = remove_collection(collection)
        result["mode"] = "collection"
        return result
    except Exception as exc:
        _log_tool_error("delete_documents", exc)
        return {
            "status": "error",
            "message": _error_message(exc),
        }
