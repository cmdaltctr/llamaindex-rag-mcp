"""Pluggable PDF reader factory and adapters.

Public API: ``get_pdf_reader()`` returns a reader adapter based on
``config.RESOLVED_PDF_READER``. See ADR-020 for the adoption rationale.

This package was relocated from ``rag_mcp/readers/`` in Phase 5.
The old path resolves via a deprecated re-export shim.
"""

from __future__ import annotations

from .factory import get_pdf_reader

__all__ = ["get_pdf_reader"]
