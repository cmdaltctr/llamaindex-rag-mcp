"""pdf-inspector adapter — Rust PDF classification and markdown extraction.

pdf-inspector (Firecrawl, MIT) classifies a PDF as text-based, scanned,
image-based, or mixed in milliseconds, then extracts position-aware text
and converts it to structured markdown — multi-column reading order,
headings, lists, and tables — without OCR or ML models. Strong on the
two-column academic layouts the Qasper corpus (Experiment 14) is built
from.

Optional dependency behind the ``pdf-inspector`` extra; the import is
lazy inside ``load_data`` per the ADR-024 pattern shared by every
optional integration.
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
            extracted markdown (empty markdown still yields a document
            with empty text so callers observe the classification).

        Raises:
            ImportError: If ``pdf_inspector`` is not installed.
        """
        try:
            import pdf_inspector
        except ImportError as exc:
            raise ImportError(
                "pdf_inspector is not installed. Install with: uv sync --extra pdf-inspector"
            ) from exc

        from llama_index.core import Document

        result = pdf_inspector.process_pdf(str(file))
        markdown = result.markdown or ""

        if result.pdf_type != "text_based":
            logger.info(
                "pdf-inspector classified %s as %s (confidence %.2f, "
                "%d page(s) may need OCR); markdown may be partial",
                file.name,
                result.pdf_type,
                result.confidence,
                len(result.pages_needing_ocr or []),
            )

        return [
            Document(
                text=markdown,
                metadata={
                    "pdf_reader": "pdf_inspector",
                    "pdf_type": result.pdf_type,
                    "pdf_confidence": result.confidence,
                    "page_count": result.page_count,
                    "file_path": str(file),
                    "file_name": file.name,
                },
            )
        ]
