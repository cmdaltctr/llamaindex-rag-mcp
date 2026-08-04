"""Deprecated shim — use ``rag_mcp.daemon.watcher`` instead.

This module re-exports the file watcher from its new home under
``daemon/``. It exists so existing ``from rag_mcp.watcher import ...``
consumers keep working during the deprecation window (removal in v2.0.0).
"""

from __future__ import annotations

import warnings

warnings.warn(
    "rag_mcp.watcher is deprecated — import from rag_mcp.daemon.watcher instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .daemon.watcher import (  # noqa: E402,F401
    CONSECUTIVE_ERROR_THRESHOLD,
    DEFAULT_DEBOUNCE_SECONDS,
    MAX_CONCURRENT_INGESTS,
    MIN_DEBOUNCE_SECONDS,
    DocumentIngestHandler,
    WatcherState,
    watch_directory,
)

__all__ = [
    "watch_directory",
    "DocumentIngestHandler",
    "WatcherState",
    "DEFAULT_DEBOUNCE_SECONDS",
    "MIN_DEBOUNCE_SECONDS",
    "MAX_CONCURRENT_INGESTS",
    "CONSECUTIVE_ERROR_THRESHOLD",
]
