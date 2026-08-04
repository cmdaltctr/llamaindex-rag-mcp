"""Deprecated shim — use ``rag_mcp.integrations.azure`` instead.

This module re-exports the Azure Document Intelligence reader from its
new home under ``integrations/``. It exists so existing
``from rag_mcp.azure_reader import ...`` consumers keep working during
the deprecation window (removal in v2.0.0).
"""

from __future__ import annotations

import warnings

warnings.warn(
    "rag_mcp.azure_reader is deprecated — import from rag_mcp.integrations.azure instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .integrations.azure import (  # noqa: E402,F401
    AzureDocReader,
    read_with_azure_fallback,
    _read_with_local_chain,
)

__all__ = ["AzureDocReader", "read_with_azure_fallback"]
