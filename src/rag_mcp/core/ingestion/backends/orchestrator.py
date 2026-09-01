"""Fallback orchestration for document-backend dispatch (design D1/D3).

The registry is a dispatch table; THIS module owns the retry budget and
the local-first fallback policy, so adding a backend never requires
strategy-specific branching here — the orchestrator reads the target's
registered metadata (``fallback``, ``document_suffixes``,
``structured_output``) and applies one generic workflow:

1. Suffix gate — a backend whose ``document_suffixes`` excludes the
   file reads through its declared fallback instead (the historical
   Azure reach was ``.pdf``/``.docx``/``.doc`` only; a ``.md`` under
   azure always read locally and still does).
2. Unavailable backend (``ImportError``) — degrade to the fallback
   immediately, no retries, with a diagnostic naming the missing
   dependency.  The result carries the FALLBACK's semantics: the
   backend cannot run, so the read is wholesale local.
3. Runtime failure — retry the configured budget, then hand the file
   to the fallback ONCE (no double-reading) with a diagnostic naming
   the backend failure as the fallback reason.  The result keeps the
   SELECTED backend's semantics: the fallback is a read substitution,
   not a reconfiguration.
4. A backend without a registered fallback gets a single attempt and
   its exceptions propagate.

Startup-phase degradation (missing credentials in ``config/``, missing
SDK in ``compose``) happens BEFORE any read; the phases stay
distinguishable by their diagnostics (design D3).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, NamedTuple

from ...settings import EffectiveSettings
from .contract import DocumentBackend
from .registry import describe, get

logger = logging.getLogger(__name__)

#: Retry budget owned by the orchestrator (design D1): one retry after
#: the initial attempt, matching the pre-registry Azure behaviour.
MAX_RETRIES = 1
#: Delay between retry attempts, in seconds.
RETRY_DELAY_S = 5.0


class BackendRead(NamedTuple):
    """Result of a dispatched document read.

    Attributes:
        documents: LlamaIndex ``Document`` objects from the reader that
            parsed the file (the selected backend, or its fallback).
        structured: Whether the documents are pre-structured (cloud
            parsers returning paragraphs/tables); drives the chunker's
            post-processing choice.
        text_format: The declared emitted-text format of the backend whose
            semantics apply (``"plain"``/``"markdown"``); drives Markdown
            routing in the chunker. This VERIFIES the pre-resolved value
            the pipeline folds into ``source_index_identity`` — it is not
            where identity first learns it (design D3).
    """

    documents: list[Any]
    structured: bool
    text_format: str


def _declared_text_format(
    meta: dict[str, Any],
    file_path: Path,
    settings: EffectiveSettings,
) -> str:
    """Return the declared text format for *file_path* under *meta*.

    A static declaration is definitive. The ``local`` chain's dynamic
    ``None`` declaration resolves from the configured PDF reader for
    ``.pdf`` files (the reader registry owns the format) and ``plain``
    for everything else.
    """
    declared = meta["text_format"]
    if declared is not None:
        return declared
    if file_path.suffix.lower() == ".pdf":
        from rag_mcp.integrations.pdf.factory import declared_text_format

        return declared_text_format(settings.pdf_reader)
    return "plain"


def resolve_declared_text_format(file_path: Path, *, settings: EffectiveSettings) -> str:
    """Resolve the declared emitted-text format for *file_path* pre-read.

    THE shared pre-read resolver (design D3): the ingestion pipeline calls
    it before the unchanged check so ``parser.text_format`` participates
    in ``source_index_identity``, and ``read_document`` verifies its own
    stamped ``BackendRead.text_format`` against the same resolution. It
    applies the suffix gate, so a gated file reports the fallback
    backend's declaration exactly as the read will.
    """
    _, meta = _select(file_path, settings.document_backend)
    return _declared_text_format(meta, file_path, settings)


def _select(file_path: Path, name: str) -> tuple[str, dict[str, Any]]:
    """Apply the suffix gate and return the backend that reads *file_path*.

    Args:
        file_path: File about to be read.
        name: Configured backend name.

    Returns:
        ``(selected_name, metadata)`` — the gated backend and its
        registry metadata.
    """
    meta = describe(name)
    suffixes = meta["document_suffixes"]
    if suffixes is not None and file_path.suffix.lower() not in suffixes:
        fallback = meta["fallback"]
        if fallback is not None:
            logger.debug(
                "Document backend %r does not handle suffix %r (%s) — using %r",
                name,
                file_path.suffix.lower(),
                file_path.name,
                fallback,
            )
            return fallback, describe(fallback)
    return name, meta


def _verify_text_format(
    stamped: str,
    *,
    file_path: Path,
    settings: EffectiveSettings,
    degraded: bool,
) -> None:
    """Verify the stamped format agrees with the pre-read resolver (D3).

    Clean and runtime-fallback reads MUST agree with the pre-read
    resolver — a divergence there is a wiring bug and fails loudly. A
    wholesale degradation (missing optional dependency) legitimately
    substitutes the fallback backend's declaration, so it warns instead:
    the read still succeeded, only the identity-era declaration moved.

    Raises:
        RuntimeError: When the stamped format disagrees with the resolver
            and no wholesale degradation explains the difference.
    """
    expected = resolve_declared_text_format(file_path, settings=settings)
    if stamped == expected:
        return
    if degraded:
        logger.warning(
            "Backend text format %r for %s differs from the pre-resolved "
            "%r because the selected backend was unavailable and the read "
            "degraded wholesale to the fallback backend.",
            stamped,
            file_path.name,
            expected,
        )
        return
    raise RuntimeError(
        f"BackendRead.text_format {stamped!r} disagrees with the "
        f"pre-resolved parser.text_format {expected!r} for "
        f"{file_path.name} (design D3)."
    )


async def read_document(file_path: Path, *, settings: EffectiveSettings) -> BackendRead:
    """Read *file_path* through the configured document backend.

    Args:
        file_path: File to read.
        settings: Injected effective settings; ``settings.document_backend``
            selects the registered backend name.

    Returns:
        A :class:`BackendRead` carrying the parsed documents, the
        structured flag, and the declared text format of the backend
        whose semantics apply.

    Raises:
        KeyError: Unknown backend name (lists the registered names).
        Exception: Reader failures once the retry budget and the single
            fallback attempt are exhausted.
    """
    selected, meta = _select(file_path, settings.document_backend)
    reader: DocumentBackend = get(selected)
    fallback_name = meta["fallback"]

    if fallback_name is None:
        # Base-install path: one attempt, exceptions propagate.
        documents = await reader(file_path, settings=settings)
        text_format = _declared_text_format(meta, file_path, settings)
        _verify_text_format(text_format, file_path=file_path, settings=settings, degraded=False)
        return BackendRead(documents, meta["structured_output"], text_format)

    unavailable = False
    for attempt in range(MAX_RETRIES + 1):
        try:
            documents = await reader(file_path, settings=settings)
            text_format = _declared_text_format(meta, file_path, settings)
            _verify_text_format(text_format, file_path=file_path, settings=settings, degraded=False)
            return BackendRead(documents, meta["structured_output"], text_format)
        except ImportError as exc:
            # The backend cannot run in this install (missing optional
            # dependency): skip the retry budget and degrade wholesale.
            logger.warning(
                "Document backend %r is unavailable (%s) — degrading to %r for %s",
                selected,
                exc,
                fallback_name,
                file_path.name,
            )
            unavailable = True
            break
        except Exception as exc:
            if attempt < MAX_RETRIES:
                logger.warning(
                    "Document backend %r attempt %d failed for %s: %s — retrying in %.1fs",
                    selected,
                    attempt + 1,
                    file_path.name,
                    exc,
                    RETRY_DELAY_S,
                )
                await asyncio.sleep(RETRY_DELAY_S)
            else:
                logger.warning(
                    "Document backend %r failed for %s after %d attempts: %s — falling back to %r",
                    selected,
                    file_path.name,
                    MAX_RETRIES + 1,
                    exc,
                    fallback_name,
                )

    fallback_reader: DocumentBackend = get(fallback_name)
    documents = await fallback_reader(file_path, settings=settings)
    if unavailable:
        # Wholesale degradation: the FALLBACK's semantics apply, including
        # its (possibly dynamic) text format.
        fallback_meta = describe(fallback_name)
        text_format = _declared_text_format(fallback_meta, file_path, settings)
        _verify_text_format(text_format, file_path=file_path, settings=settings, degraded=True)
        return BackendRead(documents, fallback_meta["structured_output"], text_format)
    # Runtime fallback keeps the SELECTED entry's semantics: the fallback
    # is a read substitution, not a reconfiguration (design D3).
    text_format = _declared_text_format(meta, file_path, settings)
    _verify_text_format(text_format, file_path=file_path, settings=settings, degraded=False)
    return BackendRead(documents, meta["structured_output"], text_format)
