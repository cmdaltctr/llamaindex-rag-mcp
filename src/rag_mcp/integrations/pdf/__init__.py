"""Registry-backed PDF reader factory and adapters.

Public API: :func:`get_pdf_reader` returns a reader adapter from the
composition-root-resolved ``EffectiveSettings.pdf_reader`` name. ``auto``
remains an ordered capability policy; concrete readers resolve lazily through
``integrations.pdf.registry``. See ADR-020 for the adoption rationale.
"""

from __future__ import annotations

from .factory import get_pdf_reader

__all__ = ["get_pdf_reader"]
