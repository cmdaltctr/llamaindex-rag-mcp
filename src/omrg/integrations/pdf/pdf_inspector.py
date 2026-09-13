"""pdf-inspector adapter — Rust PDF classification and markdown extraction.

pdf-inspector (Firecrawl, MIT) classifies a PDF as text-based, scanned,
image-based, or mixed in milliseconds, then extracts position-aware text
and converts it to structured markdown — multi-column reading order,
headings, lists, and tables — without OCR or ML models. Strong on the
two-column academic layouts the Qasper corpus (Experiment 14) is built
from.

Base dependency and the configured default reader (ADR-050); the
import stays lazy inside ``load_data`` per the ADR-024 pattern shared
by the integrations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PdfInspectorReader:
    """Adapter wrapping pdf-inspector for whole-document markdown extraction.

    Produces a single ``Document`` per file carrying the extracted
    markdown plus classification diagnostics (``pdf_type``,
    ``confidence``, ``page_count``) so downstream consumers can route on
    them (e.g. scanned PDFs to an OCR path).
    """

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        """Parse a PDF into markdown via pdf-inspector.

        Args:
            file: Path to the PDF file.

        Returns:
            List with one LlamaIndex ``Document`` whose text is the
            extracted markdown. When pdf-inspector classifies the file
            ``text_based`` yet extracts nothing from a non-empty page
            count, the document text is the pypdf retry's joined pages
            instead (empty markdown still yields a document with empty
            text so callers observe the classification).

        Raises:
            ImportError: If ``pdf_inspector`` is not installed.
            Exception: Whatever the pypdf retry raises — a file that
                opens in pdf-inspector but crashes pypdf is genuinely
                broken input for the per-file error boundary.
        """
        try:
            import pdf_inspector
        except ImportError as exc:
            raise ImportError("pdf_inspector is not installed. Install with: uv sync") from exc

        from llama_index.core import Document

        result = pdf_inspector.process_pdf(str(file))
        markdown = result.markdown or ""
        # Store-compatible scalar count (task 2.10): vector-store
        # metadata values are scalars in both backends and nothing
        # sanitises them on the way in, so the classifier's page LIST
        # is reduced here to the count the routing gate consumes.
        pages_needing_ocr_count = len(result.pages_needing_ocr or [])

        metadata: dict[str, Any] = {
            "pdf_reader": "pdf_inspector",
            "pdf_type": result.pdf_type,
            "pdf_confidence": result.confidence,
            "page_count": result.page_count,
            "pages_needing_ocr": pages_needing_ocr_count,
            "file_path": str(file),
            "file_name": file.name,
        }

        if result.pdf_type != "text_based":
            logger.info(
                "pdf-inspector classified %s as %s (confidence %.2f, "
                "%d page(s) may need OCR); markdown may be partial",
                file.name,
                result.pdf_type,
                result.confidence,
                pages_needing_ocr_count,
            )

        # Sloman guard (design D6): a ``text_based`` classification with
        # an empty extraction on a non-empty document is a contradiction —
        # the classifier saw a text layer the extractor failed to read
        # (WinAnsi TrueType fonts with no /ToUnicode map; TDR-024). Retry
        # once through the registered plain-text reader before emitting
        # zero characters. Exceptions from the retry propagate (D3).
        if result.pdf_type == "text_based" and markdown == "" and result.page_count > 0:
            from .registry import get as _get_reader

            recovered = _get_reader("pypdf")().load_data(file)
            joined = "\n\n".join(doc.text for doc in recovered if doc.text and doc.text.strip())
            if joined:
                logger.warning(
                    "pdf-inspector extracted no text from %s despite a "
                    "text_based classification (%d page(s) flagged); "
                    "recovered %d characters via pypdf",
                    file.name,
                    pages_needing_ocr_count,
                    len(joined),
                )
                markdown = joined
                # Evidence correction, not replacement (D4): the pages
                # were flagged only by the failed extraction, so the
                # scalar the OCR gate reads drops to zero while the
                # original count survives under a diagnostic key.
                metadata["pages_needing_ocr"] = 0
                metadata["pages_needing_ocr_before_fallback"] = pages_needing_ocr_count
                metadata["extraction_fallback_backend"] = "pypdf"
            else:
                logger.warning(
                    "pdf-inspector extracted no text from %s despite a "
                    "text_based classification, and the pypdf retry "
                    "recovered nothing either — emitting the flagged "
                    "evidence unchanged for OCR routing",
                    file.name,
                )

        return [Document(text=markdown, metadata=metadata)]
