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

#: Items wider than this share of the page's horizontal text extent are
#: running heads, full-width figures or rules. They bridge a gutter, so the
#: gutter test ignores them (change liteparse-reading-order, design decision 2).
_FULL_WIDTH_SHARE = 0.6
#: Bins used to sample horizontal coverage across the page.
_COVERAGE_BINS = 200
#: A bin belongs to a gutter when its coverage is at most this share of the
#: busiest bin.
_GUTTER_COVERAGE_SHARE = 0.05
#: A gutter's centre must lie inside this band of the text extent.
_GUTTER_CENTRE_MIN = 0.35
_GUTTER_CENTRE_MAX = 0.65
#: Narrowest gutter accepted, as a share of the text extent.
_MIN_GUTTER_SHARE = 0.01
#: The smaller side must hold at least this share of the larger side's items.
_MIN_SIDE_BALANCE = 0.5
#: Each side must span at least this share of the page's vertical text extent.
_MIN_SIDE_HEIGHT_SHARE = 0.5
#: Fewer items than this cannot establish a layout.
_MIN_ITEMS = 10
#: Gutters are counted only inside this band, so a sparse outer margin is not
#: mistaken for one. A two-column page has exactly one gutter; a table has
#: several, and is left alone.
_GUTTER_SEARCH_MIN = 0.1
_GUTTER_SEARCH_MAX = 0.9


def _gutter_centre(items: list[Any]) -> float | None:
    """Return the centre of the page's column gutter, or ``None``.

    The centre is a share of the page's horizontal text extent, so it can be
    compared with any item's relative position. ``None`` means the page is not
    confidently multi-column and must keep the order LiteParse returned.

    Depends only on the geometry of the page's own text items. Every threshold
    is a measured boundary from Experiment 33; see the change's design.

    Args:
        items: The page's LiteParse text items.

    Returns:
        The gutter centre as a share of the text extent, or ``None``.
    """
    if len(items) < _MIN_ITEMS:
        return None
    left_edge = min(item.x for item in items)
    extent = max(item.x + item.width for item in items) - left_edge
    if extent <= 0:
        return None

    body = [item for item in items if item.width <= _FULL_WIDTH_SHARE * extent]
    if len(body) < _MIN_ITEMS:
        return None

    last = _COVERAGE_BINS - 1
    coverage = [0] * _COVERAGE_BINS
    for item in body:
        start = int((item.x - left_edge) / extent * last)
        end = int((item.x + item.width - left_edge) / extent * last)
        for index in range(max(0, start), min(last, end) + 1):
            coverage[index] += 1
    peak = max(coverage)
    if not peak:
        return None

    bands = _gutter_bands(coverage, _GUTTER_COVERAGE_SHARE * peak)
    if len(bands) != 1:
        # No gutter, or several: a table or a grid, which is left alone.
        return None
    centre = bands[0]
    if not _GUTTER_CENTRE_MIN <= centre <= _GUTTER_CENTRE_MAX:
        return None
    left = [item for item in body if _relative_centre(item, left_edge, extent) < centre]
    right = [item for item in body if _relative_centre(item, left_edge, extent) >= centre]
    if not left or not right:
        return None
    if min(len(left), len(right)) / max(len(left), len(right)) < _MIN_SIDE_BALANCE:
        return None

    height = max(item.y for item in body) - min(item.y for item in body)
    if height <= 0:
        return None
    for side in (left, right):
        span = max(item.y for item in side) - min(item.y for item in side)
        if span / height < _MIN_SIDE_HEIGHT_SHARE:
            return None
    return centre


def _gutter_bands(coverage: list[int], threshold: float) -> list[float]:
    """Return the centre of every gutter-wide band of low coverage.

    Args:
        coverage: Item counts per horizontal bin.
        threshold: Highest count a bin may hold and still be a gutter.

    Returns:
        Each qualifying band's centre, as a share of the text extent.
    """
    centres: list[float] = []
    run = 0
    run_start = 0
    for index in range(len(coverage) + 1):
        low = index < len(coverage) and coverage[index] <= threshold
        if low:
            if run == 0:
                run_start = index
            run += 1
            continue
        if run:
            centre = (run_start + run / 2) / len(coverage)
            wide = run / len(coverage) >= _MIN_GUTTER_SHARE
            inside = _GUTTER_SEARCH_MIN <= centre <= _GUTTER_SEARCH_MAX
            if wide and inside:
                centres.append(centre)
        run = 0
    return centres


def _relative_centre(item: Any, left_edge: float, extent: float) -> float:
    """Return an item's horizontal centre as a share of the text extent."""
    return (item.x + item.width / 2 - left_edge) / extent


def _order_by_column(items: list[Any], gutter: float) -> list[Any]:
    """Return *items* in reading order: first column top to bottom, then the next.

    Args:
        items: The page's LiteParse text items.
        gutter: The gutter centre from :func:`_gutter_centre`.

    Returns:
        The same items, reordered. Nothing is added, dropped or altered.
    """
    left_edge = min(item.x for item in items)
    extent = max(item.x + item.width for item in items) - left_edge
    return sorted(
        items,
        key=lambda item: (
            0 if _relative_centre(item, left_edge, extent) < gutter else 1,
            round(item.y, 1),
            item.x,
        ),
    )


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
            gutter = _gutter_centre(page.text_items)
            if gutter is None:
                ordered = list(page.text_items)
            else:
                ordered = _order_by_column(page.text_items, gutter)
            page_text = "\n".join(item.text for item in ordered)
            if not page_text.strip():
                continue

            if gutter is not None:
                column = "multi_column"
            elif page.text_items:
                # Legacy label for a page the gutter test did not recognise:
                # left or right by where the first item sits (ADR-020).
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
