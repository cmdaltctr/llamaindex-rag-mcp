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

    This transport is the context boundary (design D3): it resolves the
    composed settings and store here and passes them to core explicitly.
    When no store is composed, the map is built store-less (empty document
    communities), which keeps the earlier graceful degradation.

    Returns a JSON error string on failure (gotcha #1).
    """
    import json

    try:
        from ...core import vectordb
        from ...core.codebase import codebase_map
        from ...core.settings import get_default_effective_settings

        settings = get_default_effective_settings()
        try:
            store = vectordb.get_default_store()
        except RuntimeError as exc:
            _log_tool_error("get_codebase_map store (building without documents)", exc)
            store = None

        return codebase_map.get_codebase_map_text(
            path=path, refresh=refresh, settings=settings, store=store
        )
    except Exception as exc:
        _log_tool_error("get_codebase_map", exc)
        return json.dumps(
            {
                "status": "error",
                "message": _error_message(exc),
            }
        )
