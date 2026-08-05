"""Factory function returning the resolved PDF reader adapter.

Mirrors the ``HYBRID_SPARSE_BACKEND`` resolver pattern in ``config.py``.
The adapter choice is driven by ``config.reader``, computed
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
        ``LiteParseReader`` based on ``reader``.

    Raises:
        ValueError: If ``reader`` is an unknown value.
            This should be unreachable because ``config.py`` validates.
    """
    global _pdf_reader_logged
    from ...core.settings import get_default_effective_settings

    reader = get_default_effective_settings().pdf_reader

    if reader == "auto":
        # compose.py normally bakes the resolved backend in, so "auto" only
        # reaches here when settings were built directly (tests, or a caller
        # bypassing the composition root). Resolve it the same way compose
        # would rather than failing.
        try:
            import liteparse  # noqa: F401

            reader = "liteparse"
        except ImportError:
            reader = "pypdf"

    if not _pdf_reader_logged:
        logger.info("PDF reader backend: %s", reader)
        _pdf_reader_logged = True

    if reader == "pypdf":
        from .pypdf import PyPDFReader
        return PyPDFReader()
    elif reader == "pypdfium2":
        from .pypdfium import PyPDFium2Reader
        return PyPDFium2Reader()
    elif reader == "liteparse":
        from .liteparse import LiteParseReader
        return LiteParseReader()
    else:
        raise ValueError(
            f"Unknown reader={reader!r}. "
            f"This should be unreachable — config.py validates accepted "
            f"values. Check for a config import error."
        )
