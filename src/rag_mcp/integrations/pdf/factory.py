"""Factory returning a PDF reader resolved through the adapter registry.

The caller passes the reader name (``EffectiveSettings.pdf_reader``); the
factory performs no settings lookup of its own. ``auto`` remains a
capability-resolution policy for callers that bypass the composition root:
the factory probes LiteParse → pypdfium2 → pypdf locally, matching the
composition root's preference order. Concrete construction then goes through
``integrations.pdf.registry`` so adding another configured reader needs one
adapter plus one ``register()`` call, with no strategy-specific branch here.
"""

from __future__ import annotations

import logging
from typing import Any

from .registry import available as _available_readers
from .registry import get as _get_reader

logger = logging.getLogger(__name__)

_pdf_reader_logged: set[str] = set()


def get_pdf_reader(reader: str) -> Any:
    """Return the PDF reader adapter for *reader*.

    The returned object has a ``load_data(file: Path) -> list[Document]``
    method, compatible with LlamaIndex's ``SimpleDirectoryReader``
    ``file_extractor`` parameter.

    Args:
        reader: Reader name from the injected settings — ``pypdf``,
            ``pypdfium2``, ``liteparse``, or ``auto``. ``auto`` is resolved
            locally (LiteParse → pypdfium2 → pypdf) for callers that bypass
            the composition root.

    Returns:
        An instance of ``PyPDFReader``, ``PyPDFium2Reader``, or
        ``LiteParseReader``.

    Raises:
        ValueError: If *reader* is an unknown value. This should be
            unreachable because the ``config`` package validates.
    """
    if reader == "auto":
        # compose.py normally bakes the resolved backend in, so "auto" only
        # reaches here when settings were built directly (tests, or a caller
        # bypassing the composition root). Resolve it the same way compose
        # would rather than failing.
        reader = _resolve_auto()

    if reader not in _pdf_reader_logged:
        logger.info("PDF reader backend: %s", reader)
        _pdf_reader_logged.add(reader)

    try:
        reader_class = _get_reader(reader)
    except KeyError as exc:
        raise ValueError(
            f"Unknown reader={reader!r}. Available concrete readers: "
            f"{', '.join(_available_readers())}. The 'auto' value is a "
            "factory capability policy, not a registered reader."
        ) from exc
    return reader_class()


def _resolve_auto() -> str:
    """Probe optional backends in the composition root's preference order."""
    for backend in ("liteparse", "pypdfium2"):
        try:
            __import__(backend)
        except ImportError:
            continue
        return backend
    return "pypdf"
