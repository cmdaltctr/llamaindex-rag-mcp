"""Experiment 31 script-local reader mirrors (tasks 3.2, 3.4).

Production has no setting that disables the fallback chain or selects a
single tier, so Cell A (pdf-inspector only) and Cell C (historical
pypdf-only guard, commit 928f030) are reproduced as script-local mirrors
registered into ``integrations.pdf.registry`` — the sanctioned dispatch
mechanism (architecture invariant #11). Production code is untouched.

Cell B (candidate) needs no mirror: it IS the production
``PdfInspectorReader`` with its ADR-066 chain, selected by registry name.

Both mirrors declare ``text_format="markdown"`` and
``page_provenance=False`` — identical to the production pdf_inspector
registration — so every cell routes through the same markdown chunking
path (ADR-055) and the reader is the only manipulated variable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MIRROR_MODULE = "harness_readers"  # importable when the experiment dir is on sys.path


def _classify(file: Path) -> tuple[Any, str, dict[str, Any]]:
    """Run the shared first tier: pdf-inspector classification + extraction."""
    import pdf_inspector

    result = pdf_inspector.process_pdf(str(file))
    markdown = result.markdown or ""
    pages_needing_ocr_count = len(result.pages_needing_ocr or [])
    metadata: dict[str, Any] = {
        "pdf_reader": MIRROR_MODULE,
        "pdf_type": result.pdf_type,
        "pdf_confidence": result.confidence,
        "page_count": result.page_count,
        "pages_needing_ocr": pages_needing_ocr_count,
        "file_path": str(file),
        "file_name": file.name,
    }
    return result, markdown, metadata


class Exp31InspectorOnlyReader:
    """Cell A mirror: pdf-inspector only — the rescue never fires."""

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        """Classify and extract; stop at the pdf-inspector result.

        A silent-empty ``text_based`` extraction stays empty: that zero is
        the sanity-check observable for every measured PDF.
        """
        from llama_index.core import Document

        result, markdown, metadata = _classify(file)
        if result.pdf_type == "text_based" and markdown == "" and result.page_count > 0:
            logger.info(
                "cell A observed the rescue trigger on %s; extraction stays empty",
                file.name,
            )
        return [Document(text=markdown, metadata=metadata)]


class Exp31PypdfGuardReader:
    """Cell C mirror: the historical pypdf-only guard (commit 928f030).

    Reproduces the guard exactly: pdf-inspector classify, then a single
    pypdf retry on the silent-empty contradiction, with the same evidence
    correction. pypdf exceptions propagate (guard D3 — no swallowing).
    """

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        from llama_index.core import Document

        result, markdown, metadata = _classify(file)
        if result.pdf_type == "text_based" and markdown == "" and result.page_count > 0:
            from omrg.integrations.pdf.registry import get as _get_reader

            recovered = _get_reader("pypdf")().load_data(file)
            joined = "\n\n".join(doc.text for doc in recovered if doc.text and doc.text.strip())
            if joined:
                logger.warning(
                    "cell C guard recovered %d characters via pypdf for %s",
                    len(joined),
                    file.name,
                )
                markdown = joined
                # Evidence correction, not replacement (guard D4): the
                # OCR gate reads zero while the flagged count survives.
                metadata["pages_needing_ocr_before_fallback"] = metadata["pages_needing_ocr"]
                metadata["pages_needing_ocr"] = 0
                metadata["extraction_fallback_backend"] = "pypdf"
            else:
                logger.warning(
                    "cell C guard recovered nothing for %s; flagged evidence unchanged",
                    file.name,
                )
        return [Document(text=markdown, metadata=metadata)]


def register_mirrors() -> None:
    """Register both mirrors under experiment names (idempotent).

    Used by ``measure_extraction.py``, which resolves readers directly
    through the registry without the Settings layer.

    Raises:
        ValueError: Propagated by the registry for a bad text_format.
    """
    from omrg.integrations.pdf import registry as pdf_registry

    pdf_registry.register(
        "exp31_inspector_only",
        f"{MIRROR_MODULE}:Exp31InspectorOnlyReader",
        "pdf_inspector",
        text_format="markdown",
        page_provenance=False,
    )
    pdf_registry.register(
        "exp31_pypdf_guard",
        f"{MIRROR_MODULE}:Exp31PypdfGuardReader",
        "pdf_inspector",
        text_format="markdown",
        page_provenance=False,
    )


#: The production registry name the cells mount under. The ``Settings``
#: validator whitelists PDF_READER literals, so an experiment-name
#: PDF_READER silently falls back to ``auto`` (observed: LiteParse ran
#: for Cell A). Mounting the mirrors under the sanctioned production
#: name keeps Settings valid while the harness swaps the implementation.
PRODUCTION_NAME = "pdf_inspector"
_PRODUCTION_IMPORT = "omrg.integrations.pdf.pdf_inspector:PdfInspectorReader"

#: Logical cell reader identity -> implementation import path.
CELL_IMPLEMENTATIONS = {
    "inspector_only": f"{MIRROR_MODULE}:Exp31InspectorOnlyReader",
    "pdf_inspector": _PRODUCTION_IMPORT,
    "pypdf_guard": f"{MIRROR_MODULE}:Exp31PypdfGuardReader",
}


def install_cell_reader(logical: str) -> None:
    """Mount *logical* under the production registry name (idempotent).

    Args:
        logical: One of ``CELL_IMPLEMENTATIONS`` — the logical cell
            reader identity, recorded in manifests.

    Raises:
        KeyError: Unknown logical name.
    """
    from omrg.integrations.pdf import registry as pdf_registry

    pdf_registry.register(
        PRODUCTION_NAME,
        CELL_IMPLEMENTATIONS[logical],
        "pdf_inspector",
        text_format="markdown",
        page_provenance=False,
    )
    pdf_registry._cache.pop(PRODUCTION_NAME, None)


def restore_production_reader() -> None:
    """Re-mount the production PdfInspectorReader (idempotent)."""
    install_cell_reader("pdf_inspector")
