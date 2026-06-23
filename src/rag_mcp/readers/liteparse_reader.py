"""LiteParse adapter — spatial-aware PDF parsing with bbox metadata.

LiteParse (Rust + PDFium, Apache-2.0) is the highest-quality model-free
PDF parser available under this project's hard constraints. This adapter
captures bounding-box metadata on every emitted Document for future
spatial RAG capabilities.

Activated via ``[pdf-liteparse]`` extra. See ADR-020.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LiteParseReader:
    """Adapter wrapping LiteParse for column-aware PDF extraction.

    Produces ``Document`` objects with spatial metadata (page, column,
    ``section_bbox``, ``bbox_schema_version``) per the spec requirement.
    OCR is disabled by default (``LITEPARSE_OCR_ENABLED``).
    """

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        """Parse a PDF using LiteParse with bounding-box capture.

        Args:
            file: Path to the PDF file.

        Returns:
            List of LlamaIndex Document objects, each carrying bbox
            metadata (``page``, ``column``, ``section_bbox``,
            ``bbox_schema_version``, ``pdf_reader``).

        Raises:
            ImportError: If ``liteparse`` is not installed.
        """
        from llama_index.core import Document

        from ..config import LITEPARSE_OCR_ENABLED, LITEPARSE_NUM_WORKERS

        from liteparse import LiteParse

        parser = LiteParse(
            ocr_enabled=LITEPARSE_OCR_ENABLED,
            num_workers=LITEPARSE_NUM_WORKERS,
            quiet=True,
        )
        result = parser.parse(str(file))

        documents = []
        for page in result.pages:
            page_text = "\n".join(item.text for item in page.text_items)
            if not page_text.strip():
                continue

            # Column detection: if any item's x is < 45% of max-x and
            # another is >= 45%, the page has multiple columns.
            if page.text_items:
                max_x = max(item.x + item.width for item in page.text_items)
                has_left = any(
                    item.x < max_x * 0.45 for item in page.text_items
                )
                has_right = any(
                    item.x >= max_x * 0.45 for item in page.text_items
                )
                if has_left and has_right:
                    column = (
                        "left"
                        if page.text_items[0].x < max_x * 0.45
                        else "right"
                    )
                else:
                    column = "single"
            else:
                column = "single"

            bbox = [
                min((item.x for item in page.text_items), default=0.0),
                min((item.y for item in page.text_items), default=0.0),
                max(
                    (item.x + item.width for item in page.text_items),
                    default=0.0,
                ),
                max(
                    (item.y + item.height for item in page.text_items),
                    default=0.0,
                ),
            ]

            documents.append(Document(
                text=page_text,
                metadata={
                    "pdf_reader": "liteparse",
                    "page": page.page_num,
                    "column": column,
                    "section_bbox": json.dumps(bbox),
                    "bbox_schema_version": 1,
                    "file_path": str(file),
                    "file_name": file.name,
                },
            ))
        return documents
