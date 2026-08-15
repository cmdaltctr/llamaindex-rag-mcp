"""Factory returning a PDF reader resolved through the adapter registry.

``auto`` remains capability resolution: the composition root normally probes
LiteParse → pypdfium2 → pypdf once and injects a concrete name.  Direct test
or library callers that still carry ``auto`` keep the previous local probe
(LiteParse → pypdf).  Concrete construction then goes through
``integrations.pdf.registry`` so adding another configured reader needs one
adapter plus one ``register()`` call, with no strategy-specific branch here.
"""

from __future__ import annotations

import logging
from typing import Any

from .registry import available as _available_readers
from .registry import get as _get_reader

logger = logging.getLogger(__name__)

_pdf_reader_logged = False


def get_pdf_reader() -> Any:
    """Return the PDF reader adapter for the current configuration.

    The returned object has a ``load_data(file: Path) -> list[Document]``
    method, compatible with LlamaIndex's ``SimpleDirectoryReader``
    ``file_extractor`` parameter.

    Returns:
        An instance of ``PyPDFReader``, ``PyPDFium2Reader``, or
        ``LiteParseReader`` selected by the configured ``PDF_READER``
        value (``auto`` is resolved locally first).

    Raises:
        ValueError: If the configured reader is an unknown value.
            This should be unreachable because the ``config`` package
            validates.
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

    try:
        reader_class = _get_reader(reader)
    except KeyError as exc:
        raise ValueError(
            f"Unknown reader={reader!r}. Available concrete readers: "
            f"{', '.join(_available_readers())}. The 'auto' value is a "
            "factory capability policy, not a registered reader."
        ) from exc
    return reader_class()
