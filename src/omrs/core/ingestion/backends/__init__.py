"""Registry-backed document-backend dispatch for the ingestion pipeline.

Public surface: :func:`read_document` (orchestrated read with the retry
budget and local-first fallback) plus the lazy :mod:`registry`.
Importing this package does NOT import any concrete backend module —
backends resolve through ``"module:attr"`` import strings on first use
(spec ``document-backend-strategies``: "Backend dispatch is lazy and
extensible").
"""

from __future__ import annotations

from . import registry
from .orchestrator import BackendRead, read_document

__all__ = ["BackendRead", "read_document", "registry"]
