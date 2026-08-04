"""Deprecated shim — use ``rag_mcp.transports.mcp`` instead.

This module re-exports the MCP server from its new home under
``transports/``. It exists so existing ``from rag_mcp.server import ...``
consumers keep working during the deprecation window (removal in v2.0.0).
"""

from __future__ import annotations

import warnings

warnings.warn(
    "rag_mcp.server is deprecated — import from rag_mcp.transports.mcp instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .transports.mcp import (  # noqa: E402,F401
    change_collection_profile,
    delete_documents,
    get_codebase_map,
    ingest_documents,
    list_collections,
    list_indexed_documents,
    main,
    mcp,
    search_documents,
)

__all__ = [
    "mcp",
    "main",
    "ingest_documents",
    "search_documents",
    "list_indexed_documents",
    "list_collections",
    "delete_documents",
    "get_codebase_map",
    "change_collection_profile",
]
