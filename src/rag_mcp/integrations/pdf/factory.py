"""Factory function returning the resolved PDF reader adapter.

Mirrors the ``HYBRID_SPARSE_BACKEND`` resolver pattern in ``config.py``.
The adapter choice is driven by ``config.RESOLVED_PDF_READER``, computed
once at import time. See ADR-020 for the adoption rationale.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_pdf_reader_logged = False


def get_pdf_reader() -> Any:
    """Return the PDF reader adapter for the current configuration.

    The returned object has a ``load_data(file: Path) -> list[Document]``
    method, compatible with LlamaIndex's ``SimpleDirectoryReader``
    ``file_extractor`` parameter.

    Returns:
        An instance of ``PyPDFReader``, ``PyPDFium2Reader``, or
        ``LiteParseReader`` based on ``RESOLVED_PDF_READER``.

    Raises:
        ValueError: If ``RESOLVED_PDF_READER`` is an unknown value.
            This should be unreachable because ``config.py`` validates.
    """
    global _pdf_reader_logged
    from ...config import RESOLVED_PDF_READER

    if not _pdf_reader_logged:
        logger.info("PDF reader backend: %s", RESOLVED_PDF_READER)
        _pdf_reader_logged = True

    if RESOLVED_PDF_READER == "pypdf":
        from .pypdf import PyPDFReader
        return PyPDFReader()
    elif RESOLVED_PDF_READER == "pypdfium2":
        from .pypdfium import PyPDFium2Reader
        return PyPDFium2Reader()
    elif RESOLVED_PDF_READER == "liteparse":
        from .liteparse import LiteParseReader
        return LiteParseReader()
    else:
        raise ValueError(
            f"Unknown RESOLVED_PDF_READER={RESOLVED_PDF_READER!r}. "
            f"This should be unreachable — config.py validates accepted "
            f"values. Check for a config import error."
        )
