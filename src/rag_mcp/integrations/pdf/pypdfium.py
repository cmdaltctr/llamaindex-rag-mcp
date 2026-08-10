"""pypdfium2 adapter — same-engine fallback tier (no bbox).

pypdfium2 ships as a pure-Python wheel with a bundled PDFium binary.
It is used as a middle fallback between LiteParse (full features) and
pypdf (always available). Activated via ``[pdf-pypdfium2]`` extra.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PyPDFium2Reader:
    """Adapter wrapping pypdfium2 for PDF text extraction.

    Same PDFium engine as LiteParse but without bounding-box metadata
    or column-aware reading order. Useful when LiteParse's native build
    fails but PDFium-grade parsing is still desired.
    """

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        """Parse a PDF using pypdfium2.

        Args:
            file: Path to the PDF file.

        Returns:
            List of LlamaIndex Document objects.

        Raises:
            ImportError: If ``pypdfium2`` is not installed. The factory
                should not route here if the package is missing, but
                this guard prevents a silent crash if ``PDF_READER`` is
                set explicitly.
        """
        import pypdfium2
        from llama_index.core import Document

        pdf = pypdfium2.PdfDocument(str(file))
        documents = []
        for i in range(len(pdf)):
            page = pdf[i]
            text = page.get_textpage().get_text_range()
            if text.strip():
                documents.append(
                    Document(
                        text=text,
                        metadata={
                            "pdf_reader": "pypdfium2",
                            "page": i + 1,
                            "file_path": str(file),
                            "file_name": file.name,
                        },
                    )
                )
        pdf.close()
        return documents
