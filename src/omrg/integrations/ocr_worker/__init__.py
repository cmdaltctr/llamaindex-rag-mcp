"""OMRG-side integration for the isolated OCR worker.

Public API: the :class:`OcrWorkerClient` subprocess client, its
structured :class:`OcrWorkerError`, and the OMRG-owned copy of the
JSON Lines protocol. Nothing in this package imports from the
``ocr-workers`` projects; the two protocol copies are kept byte-identical
by tests, not by imports.
"""

from __future__ import annotations

from .client import OcrWorkerClient, OcrWorkerError
from .protocol import (
    ParseFailure,
    ParseRequest,
    ParseSuccess,
    ProtocolError,
)

__all__ = [
    "OcrWorkerClient",
    "OcrWorkerError",
    "ParseFailure",
    "ParseRequest",
    "ParseSuccess",
    "ProtocolError",
]
