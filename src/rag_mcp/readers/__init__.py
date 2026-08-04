"""Deprecated shim — use ``rag_mcp.integrations.pdf`` instead.

This package re-exports the PDF reader factory from its new home under
``integrations/pdf/``. It exists so existing ``from rag_mcp.readers
import ...`` consumers keep working during the deprecation window
(removal in v2.0.0).
"""

from __future__ import annotations

import warnings

warnings.warn(
    "rag_mcp.readers is deprecated — import from rag_mcp.integrations.pdf instead.",
    DeprecationWarning,
    stacklevel=2,
)

from ..integrations.pdf.factory import get_pdf_reader  # noqa: E402,F401

__all__ = ["get_pdf_reader"]
