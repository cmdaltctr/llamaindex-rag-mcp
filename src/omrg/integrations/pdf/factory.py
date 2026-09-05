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
from .registry import describe as _describe_reader
from .registry import get as _get_reader

logger = logging.getLogger(__name__)

_pdf_reader_logged: set[str] = set()


def resolve_reader_name(reader: str) -> str:
    """Return the concrete reader name for *reader*, resolving ``auto``.

    This is the pre-read resolver direct callers share with the composition
    root (design D3): ``auto`` keeps the established LiteParse → pypdfium2 →
    pypdf capability policy, so a caller that bypassed ``compose`` and left
    the selector at ``auto`` resolves the same concrete reader the
    composition root would have baked in.

    Args:
        reader: Reader name from the injected settings — a concrete name or
            ``auto``.

    Returns:
        The concrete registered reader name.
    """
    if reader == "auto":
        return _resolve_auto()
    return reader


def declared_text_format(reader: str) -> str:
    """Return the declared text format for a possibly-``auto`` selector.

    Args:
        reader: Reader name from the injected settings — a concrete name or
            ``auto``.

    Returns:
        ``"plain"`` or ``"markdown"`` as declared by the resolved reader.

    Raises:
        KeyError: If the resolved name is not registered (lists available
            names).
    """
    return _describe_reader(resolve_reader_name(reader))["text_format"]


def get_pdf_reader(reader: str) -> Any:
    """Return the PDF reader adapter for *reader*.

    The returned object has a ``load_data(file: Path) -> list[Document]``
    method, compatible with LlamaIndex's ``SimpleDirectoryReader``
    ``file_extractor`` parameter.

    Args:
        reader: Reader name from the injected settings — ``pdf_inspector``,
            ``pypdf``, ``pypdfium2``, ``liteparse``, or ``auto``. ``auto`` is
            resolved locally (LiteParse → pypdfium2 → pypdf) for callers that
            bypass the composition root.

    Returns:
        An instance of ``PdfInspectorReader``, ``PyPDFReader``,
        ``PyPDFium2Reader``, or ``LiteParseReader``.

    Raises:
        ValueError: If *reader* is an unknown value. This should be
            unreachable because the ``config`` package validates.
    """
    if reader == "auto":
        # compose.py normally bakes the resolved backend in, so "auto" only
        # reaches here when settings were built directly (tests, or a caller
        # bypassing the composition root). Resolve it the same way compose
        # would rather than failing.
        reader = resolve_reader_name(reader)

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
