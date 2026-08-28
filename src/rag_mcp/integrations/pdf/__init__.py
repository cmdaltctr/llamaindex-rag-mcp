"""Registry-backed PDF reader factory and adapters.

Public API: :func:`get_pdf_reader(reader)` returns a reader adapter for the
caller-supplied ``EffectiveSettings.pdf_reader`` name — the factory performs
no settings lookup of its own. ``auto`` remains an ordered capability
policy, resolved locally for callers that bypass the composition root;
concrete readers resolve lazily through ``integrations.pdf.registry``. See
ADR-020 for the adoption rationale.
"""

from __future__ import annotations

from .factory import get_pdf_reader

__all__ = ["get_pdf_reader"]
