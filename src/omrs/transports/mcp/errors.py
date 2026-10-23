"""Error text helpers for MCP tool handlers (gotcha #1, design D9).

Every helper redacts through the Engine of the request's
:class:`~omrs.transports.mcp.context.McpContext`, so stdio and HTTP remove
the same credential values. The helpers never raise.
"""

from __future__ import annotations

import logging

from .context import McpContext

#: The logger name tests and operators filter on (the package logger).
logger = logging.getLogger("omrs.transports.mcp")

_REDACTION_FAILED = "(details unavailable: error text could not be redacted)"


def error_detail(mcp: McpContext, exc: Exception) -> str:
    """Return the exception text with credential values removed."""
    try:
        return mcp.engine.redact(str(exc))
    except Exception:
        return _REDACTION_FAILED


def error_message(mcp: McpContext, exc: Exception) -> str:
    """Format a safe error message for MCP clients."""
    return f"{type(exc).__name__}: {error_detail(mcp, exc)}"


def log_tool_error(mcp: McpContext, tool: str, exc: Exception) -> None:
    """Log a tool failure without leaking credential values."""
    logger.warning("%s error: %s: %s", tool, type(exc).__name__, error_detail(mcp, exc))
