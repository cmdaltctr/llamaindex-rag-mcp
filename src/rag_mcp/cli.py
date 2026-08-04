"""Deprecated shim — use ``rag_mcp.transports.cli`` instead.

This module re-exports the CLI from its new home under ``transports/``.
It exists so existing ``from rag_mcp.cli import ...`` consumers keep
working during the deprecation window (removal in v2.0.0).
"""

from __future__ import annotations

import warnings

warnings.warn(
    "rag_mcp.cli is deprecated — import from rag_mcp.transports.cli instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .transports.cli import (  # noqa: E402,F401
    app,
    benchmark,
    console,
    ingest,
    run_cli,
)

__all__ = ["app", "run_cli", "console", "ingest", "benchmark"]
