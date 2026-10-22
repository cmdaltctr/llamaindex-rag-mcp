"""MCP server exposing RAG document tools over stdio (and HTTP via the web server).

Start with:
    uv run omrg

Tools
-----
- ingest_documents       – index a file / directory into the RAG store
- search_documents       – semantic search over the indexed documents
- answer_documents       – grounded answering with verifiable citations
- list_indexed_documents – show what's currently in the store
- list_collections       – list all ChromaDB collections with counts
- delete_documents       – remove documents by path, metadata filter, or drop collection
- get_codebase_map       – generate a compact codebase map
- change_collection_profile – change the profile bound to a collection
- list_profiles          – list built-in and user profiles

This module is the MCP transport. It validates input, delegates to the
Engine in the lifespan context, and formats output. No business logic
lives here.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from dotenv import find_dotenv, load_dotenv
from mcp.server.mcpserver import MCPServer

# The composition root owns all runtime construction. ``main()`` invokes it
# after this module has been imported, keeping imports safe for discovery and
# test collection.
from ... import compose
from ...core.settings import PROVIDER_SECRET_FIELDS
from ...core.vectordb.identity import redact_cloud_secrets, redact_secrets
from .answer import answer_documents
from .codebase import get_codebase_map
from .context import McpContext, PathPolicy, no_admission
from .delete import delete_documents
from .ingest import ingest_documents
from .list import list_collections, list_indexed_documents
from .profile import change_collection_profile, list_profiles
from .search import search_documents
from .server import create_mcp_server

__all__ = [
    "answer_documents",
    "change_collection_profile",
    "create_mcp_server",
    "delete_documents",
    "get_codebase_map",
    "ingest_documents",
    "list_collections",
    "list_indexed_documents",
    "list_profiles",
    "main",
    "search_documents",
]

logger = logging.getLogger(__name__)

# Returned by ``_error_detail`` when settings cannot be resolved; main()
# replaces this placeholder with the real startup reason (config and
# provider messages never echo key material by design).
_SETTINGS_UNRESOLVED = "(details unavailable: settings could not be resolved)"

load_dotenv(find_dotenv(usecwd=True))  # the working directory's .env, as env_file reads


def _error_detail(exc: Exception) -> str:
    """Return startup-failure text with active credentials redacted.

    Used only by :func:`main`, before an Engine exists. Handlers redact
    through the Engine (``errors.error_detail``). Chroma Cloud connection
    values and the LLM provider API keys are removed (full value and any
    prefix of six or more characters). When settings themselves cannot be
    resolved the raw text cannot be redacted, so only a placeholder is
    returned.
    """
    try:
        values = compose.redaction_values()
    except Exception:
        return _SETTINGS_UNRESOLVED
    return redact_secrets(
        redact_cloud_secrets(
            str(exc),
            values["chroma_cloud_api_key"],
            values["chroma_cloud_tenant"],
            values["chroma_cloud_database"],
        ),
        [values.get(name, "") for name in PROVIDER_SECRET_FIELDS],
    )


def _stdio_lifespan(engine: Any) -> Any:
    """Return a lifespan that yields the stdio context and closes *engine*."""

    @asynccontextmanager
    async def lifespan(_server: MCPServer[McpContext]) -> AsyncIterator[McpContext]:
        try:
            yield McpContext(engine, PathPolicy.allow_all(), no_admission)
        finally:
            engine.close()

    return lifespan


def main() -> None:
    """Start the MCP server on stdio transport."""
    import sys

    from ...config.legacy_install import exit_if_legacy_install

    exit_if_legacy_install()
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    engine = None
    try:
        # The stdio server reads user profiles from the default workspace
        # (D11): read-only, and ``None`` when the database file is missing.
        from ...compose_profile_setup import workspace_profile_catalogue

        engine = compose.build_engine(catalogue=workspace_profile_catalogue())
        # The profile resolver builds lazily; touch it so an invalid
        # profile configuration still stops startup.
        engine.profile_resolver  # noqa: B018
    except (ImportError, ValueError, RuntimeError) as exc:
        # RuntimeError carries the redacted Chroma Cloud connection
        # failure — an explicit cloud selection never falls back to a
        # local index, so startup must stop here.
        if engine is not None:
            engine.close()
        detail = _error_detail(exc)
        if detail == _SETTINGS_UNRESOLVED:
            # The caught error IS the settings failure; its message names
            # the offending variable and never echoes key material.
            detail = f"{type(exc).__name__}: {exc}"
        print(f"Error: {detail}", file=sys.stderr)
        raise SystemExit(1) from None
    create_mcp_server(_stdio_lifespan(engine)).run(transport="stdio")


if __name__ == "__main__":
    main()
