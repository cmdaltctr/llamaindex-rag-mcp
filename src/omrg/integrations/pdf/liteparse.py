"""LiteParse adapter — spatial-aware PDF parsing with bbox metadata.

LiteParse (Rust + PDFium, Apache-2.0) is the highest-quality model-free
PDF parser available under this project's hard constraints. This adapter
captures bounding-box metadata on every emitted Document for future
spatial RAG capabilities.

LiteParse is a base dependency and the default reader selected by the
composition root. See ADR-020.
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

    def __init__(
        self,
        *,
        ocr_enabled: bool | None = None,
        num_workers: int | None = None,
    ) -> None:
        """Initialise with optional self-contained parser settings.

        Args:
            ocr_enabled: When ``None`` (the registry default), the reader
                reads both parser settings from the default effective
                settings. A concrete bool makes this instance
                self-contained; the rescue tier passes ``False``.
            num_workers: Worker count paired with a concrete
                ``ocr_enabled`` value. ``None`` lets LiteParse choose
                automatically without consulting global settings.
        """
        self._ocr_enabled_override = ocr_enabled
        self._num_workers_override = num_workers

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
        from liteparse import LiteParse
        from llama_index.core import Document

        if self._ocr_enabled_override is None:
            from ...core.settings import get_default_effective_settings

            defaults = get_default_effective_settings()
            ocr_enabled = defaults.liteparse_ocr_enabled
            num_workers = defaults.liteparse_num_workers
        else:
            ocr_enabled = self._ocr_enabled_override
            num_workers = self._num_workers_override

        parser = LiteParse(
            ocr_enabled=ocr_enabled,
            num_workers=num_workers,
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
                has_left = any(item.x < max_x * 0.45 for item in page.text_items)
                has_right = any(item.x >= max_x * 0.45 for item in page.text_items)
                if has_left and has_right:
                    column = "left" if page.text_items[0].x < max_x * 0.45 else "right"
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

            documents.append(
                Document(
                    text=page_text,
                    metadata={
                        "pdf_reader": "liteparse",
                        "page": page.page_num,
                        # String page label matching pypdf's format: the
                        # 1-based page number as a string. This is the key
                        # retrieval reads (spec pdf-reader: "Page provenance
                        # is honest per reader") — liteparse observes page
                        # boundaries, so it says so.
                        "page_label": str(page.page_num),
                        "column": column,
                        "section_bbox": json.dumps(bbox),
                        "bbox_schema_version": 1,
                        "file_path": str(file),
                        "file_name": file.name,
                    },
                )
            )
        return documents
