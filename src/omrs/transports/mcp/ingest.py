"""MCP tool: ingest_documents."""

from __future__ import annotations

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from .context import PathDenied, mcp_context
from .errors import error_detail, error_message, log_tool_error

DESCRIPTION = (
    "Index one or more documents or a directory into the RAG store. "
    "Accepts a file path or directory path. Optionally specify a "
    "target ChromaDB collection. Supported formats: PDF, "
    "DOCX, PPTX, TXT, Markdown, HTML, CSV."
)
ANNOTATIONS = ToolAnnotations(read_only_hint=False, destructive_hint=True)


async def ingest_documents(path: str, collection: str = "documents", *, ctx: Context) -> dict:
    """Index documents into the RAG vector store.

    Over HTTP the path must lie inside an approved ``--root`` directory.
    Returns an error dict on any failure (gotcha #1 — never raise from
    MCP tool handlers).
    """
    mcp = mcp_context(ctx)
    try:
        checked = mcp.paths.check(path)
    except PathDenied as exc:
        return {"status": "error", "message": str(exc)}
    try:
        mcp.engine.resolve_settings(collection)
    except ValueError as exc:
        return {"status": "error", "message": error_detail(mcp, exc)}
    except Exception as exc:
        log_tool_error(mcp, "ingest_documents setup", exc)
        return {"status": "error", "message": error_message(mcp, exc)}
    try:
        async with mcp.admit():
            return await mcp.engine.ingest(checked, collection_name=collection)
    except Exception as exc:
        log_tool_error(mcp, "ingest_documents", exc)
        return {
            "status": "error",
            "message": error_message(mcp, exc),
        }
