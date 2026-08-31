"""MCP tool: get_codebase_map."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from . import _error_message, _log_tool_error, mcp


@mcp.tool(
    description=(
        "Generate a compact codebase map showing file types, code communities, "
        "document communities, cross-links, and architectural hubs. Useful for "
        "agents starting a session on an unfamiliar codebase. Results are cached "
        "per-project keyed by git commit hash. Use refresh=true to force rebuild."
    ),
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
)
def get_codebase_map(path: str = ".", refresh: bool = False) -> str:
    """Generate a compact codebase map for the given project path.

    Returns a JSON error string on failure (gotcha #1).
    """
    import json

    try:
        from ...core.codebase.codebase_map import get_codebase_map_text

        return get_codebase_map_text(path=path, refresh=refresh)
    except Exception as exc:
        _log_tool_error("get_codebase_map", exc)
        return json.dumps(
            {
                "status": "error",
                "message": _error_message(exc),
            }
        )
