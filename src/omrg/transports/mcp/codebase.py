"""MCP tool: get_codebase_map."""

from __future__ import annotations

import asyncio
import json

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from ...core.codebase import codebase_map
from .context import PathDenied, mcp_context
from .errors import error_message, log_tool_error

DESCRIPTION = (
    "Generate a compact codebase map showing file types, code communities, "
    "document communities, cross-links, and architectural hubs. Useful for "
    "agents starting a session on an unfamiliar codebase. Results are cached "
    "per-project keyed by git commit hash. Use refresh=true to force rebuild."
)
ANNOTATIONS = ToolAnnotations(read_only_hint=True, destructive_hint=False)


async def get_codebase_map(path: str = ".", refresh: bool = False, *, ctx: Context) -> str:
    """Generate a compact codebase map for the given project path.

    This transport is the context boundary (design D3): it resolves the
    composed settings and store from the Engine and passes them to core
    explicitly. Over HTTP the path must lie inside an approved ``--root``.

    Returns a JSON error string on failure (gotcha #1).
    """
    mcp = mcp_context(ctx)
    try:
        checked = mcp.paths.check(path)
    except PathDenied as exc:
        return json.dumps({"status": "error", "message": str(exc)})
    try:
        async with mcp.admit():
            return await asyncio.to_thread(
                codebase_map.get_codebase_map_text,
                path=checked,
                refresh=refresh,
                settings=mcp.engine.resolve_settings(None),
                store=mcp.engine.store,
            )
    except Exception as exc:
        log_tool_error(mcp, "get_codebase_map", exc)
        return json.dumps(
            {
                "status": "error",
                "message": error_message(mcp, exc),
            }
        )
