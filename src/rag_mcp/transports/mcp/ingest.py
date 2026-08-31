"""MCP tool: ingest_documents."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from ...core.ingestion import ingest_path_async
from . import _error_detail, _error_message, _get_profile_resolver, _log_tool_error, mcp


@mcp.tool(
    description=(
        "Index one or more documents or a directory into the RAG store. "
        "Accepts a file path or directory path. Optionally specify a "
        "target ChromaDB collection. Supported formats: PDF, "
        "DOCX, PPTX, TXT, Markdown, HTML, CSV."
    ),
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
)
async def ingest_documents(path: str, collection: str = "documents") -> dict:
    """Index documents into the RAG vector store.

    Returns an error dict on any failure (gotcha #1 — never raise from
    MCP tool handlers).
    """
    try:
        effective = _get_profile_resolver().resolve(collection)
    except ValueError as exc:
        return {"status": "error", "message": _error_detail(exc)}
    except Exception as exc:
        _log_tool_error("ingest_documents setup", exc)
        return {"status": "error", "message": _error_message(exc)}
    try:
        return await ingest_path_async(
            path, collection_name=collection, effective_settings=effective
        )
    except Exception as exc:
        _log_tool_error("ingest_documents", exc)
        return {
            "status": "error",
            "message": _error_message(exc),
        }
