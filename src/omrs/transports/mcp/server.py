"""MCP server factory (design D1).

``create_mcp_server(lifespan)`` builds a server and registers every tool on
it. Importing this module has no side effect: there is no module-level
server. Stdio and HTTP each pass their own lifespan, which yields the
:class:`~omrs.transports.mcp.context.McpContext` the handlers read.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import answer, codebase, delete, ingest, profile, search
from . import list as list_tools
from .context import McpContext

#: ``(handler, description, annotations)`` for each tool. The handler name
#: is the tool name.
_TOOLS: tuple[tuple[Callable[..., Any], str, ToolAnnotations], ...] = (
    (ingest.ingest_documents, ingest.DESCRIPTION, ingest.ANNOTATIONS),
    (search.search_documents, search.DESCRIPTION, search.ANNOTATIONS),
    (answer.answer_documents, answer.DESCRIPTION, answer.ANNOTATIONS),
    (
        list_tools.list_indexed_documents,
        list_tools.LIST_DOCUMENTS_DESCRIPTION,
        list_tools.ANNOTATIONS,
    ),
    (
        list_tools.list_collections,
        list_tools.LIST_COLLECTIONS_DESCRIPTION,
        list_tools.ANNOTATIONS,
    ),
    (delete.delete_documents, delete.DESCRIPTION, delete.ANNOTATIONS),
    (codebase.get_codebase_map, codebase.DESCRIPTION, codebase.ANNOTATIONS),
    (profile.change_collection_profile, profile.DESCRIPTION, profile.ANNOTATIONS),
    (profile.list_profiles, profile.LIST_DESCRIPTION, profile.LIST_ANNOTATIONS),
)

Lifespan = Callable[[MCPServer[McpContext]], AbstractAsyncContextManager[McpContext]]


def register_tools(server: MCPServer[McpContext]) -> None:
    """Register every OMRS tool on *server*."""
    for handler, description, tool_annotations in _TOOLS:
        server.tool(description=description, annotations=tool_annotations)(handler)


def create_mcp_server(lifespan: Lifespan) -> MCPServer[McpContext]:
    """Build an MCP server whose handlers read the context *lifespan* yields.

    Args:
        lifespan: Async context manager factory that yields an
            :class:`McpContext` and releases what it owns on exit.

    Returns:
        A server with all tools registered.
    """
    server: MCPServer[McpContext] = MCPServer("omrs", log_level="WARNING", lifespan=lifespan)
    register_tools(server)
    return server
