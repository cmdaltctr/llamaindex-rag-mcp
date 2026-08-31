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

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

# The composition root owns all runtime construction. ``main()`` invokes it
# after this module has been imported, keeping imports safe for discovery and
# test collection.
from ... import compose
from ...core.vectordb.identity import redact_cloud_secrets, redact_secret

logger = logging.getLogger(__name__)

# Returned by ``_error_detail`` when settings cannot be resolved; main()
# replaces this placeholder with the real startup reason (config and
# provider messages never echo key material by design).
_SETTINGS_UNRESOLVED = "(details unavailable: settings could not be resolved)"

# Load .env from the working directory (project root when run via `uv run`)
load_dotenv()

_reranker: Any | None = None
_profile_resolver: Any | None = None


def _get_reranker() -> Any:
    """Return the process-wide reranker after server startup."""
    global _reranker
    if _reranker is None:
        _reranker = compose.build_reranker()
    return _reranker


def _get_profile_resolver() -> Any:
    """Return the process-wide profile resolver after server startup."""
    global _profile_resolver
    if _profile_resolver is None:
        _profile_resolver = compose.build_profile_resolver()
    return _profile_resolver


def _error_detail(exc: Exception) -> str:
    """Return exception text with active credentials redacted.

    Chroma Cloud connection values and the OpenRouter API key are removed
    (full value and any prefix of six or more characters).  When settings
    themselves cannot be resolved the raw text cannot be redacted, so only
    a placeholder is returned — the helper must never raise or leak
    unredacted detail from a tool error path (gotcha #1).
    """
    try:
        settings = compose.get_settings()
    except Exception:
        return _SETTINGS_UNRESOLVED
    return redact_secret(
        redact_cloud_secrets(
            str(exc),
            settings.chroma_cloud_api_key,
            settings.chroma_cloud_tenant,
            settings.chroma_cloud_database,
        ),
        settings.openrouter_api_key,
    )


def _error_message(exc: Exception) -> str:
    """Format a safe error message for MCP clients."""
    return f"{type(exc).__name__}: {_error_detail(exc)}"


def _log_tool_error(tool: str, exc: Exception) -> None:
    """Log a tool failure without leaking cloud connection data."""
    logger.warning("%s error: %s: %s", tool, type(exc).__name__, _error_detail(exc))


# ── FastMCP lifespan (forward-compatibility slot) ──────────────────────────
# The lifespan is passed as ``None`` today. The structural slot is preserved
# so that pre-loading expensive resources (reranker ONNX model, embedding
# client, vector store connection) can be added without restructuring the
# module. See PROPOSAL §5.2 (transports/mcp.py compatibility note).


@asynccontextmanager
async def _noop_lifespan(server: MCPServer) -> AsyncIterator[dict[str, Any]]:
    """Yield an empty context — no pre-loaded resources today.

    Replacing this with a real lifespan (e.g. one that constructs the
    pipeline via ``compose.build_pipeline()``) requires no structural
    change to this module.
    """
    yield {}


mcp = MCPServer("rag-mcp", log_level="WARNING", lifespan=_noop_lifespan)


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
    try:
        compose.ensure_runtime_setup()
        _get_reranker()
        _get_profile_resolver()
    except (ImportError, ValueError, RuntimeError) as exc:
        # RuntimeError carries the redacted Chroma Cloud connection
        # failure — an explicit cloud selection never falls back to a
        # local index, so startup must stop here.
        detail = _error_detail(exc)
        if detail == _SETTINGS_UNRESOLVED:
            # The caught error IS the settings failure; its message names
            # the offending variable and never echoes key material.
            detail = f"{type(exc).__name__}: {exc}"
        print(f"Error: {detail}", file=sys.stderr)
        raise SystemExit(1) from None
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()


# Importing the handler modules below registers their ``@mcp.tool`` decorators
# (side effect of import) and re-exports each handler at the package root so
# ``from rag_mcp.transports.mcp import <handler>`` keeps working. The block sits
# at the bottom because ``mcp`` must exist before the decorators run; the
# ``noqa`` suppresses E402 (module-level import not at top) and F401 (imported
# but unused — the names are re-exports).
from .codebase import get_codebase_map  # noqa: E402,F401
from .delete import delete_documents  # noqa: E402,F401
from .ingest import ingest_documents  # noqa: E402,F401
from .list import list_collections, list_indexed_documents  # noqa: E402,F401
from .profile import change_collection_profile  # noqa: E402,F401
from .search import search_documents  # noqa: E402,F401
