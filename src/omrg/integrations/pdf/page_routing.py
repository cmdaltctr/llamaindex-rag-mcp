"""Page-unit OCR routing for the pdf-inspector path (change page-level-ocr-routing).

``OCR_ROUTING_UNIT=page`` routes a PDF page by page instead of whole. This
module holds that unit's logic, so the document unit's seam in
``ocr_routing.py`` stays the shape it has always been.

Page numbering is the trap here. pdf-inspector numbers
``extract_pages_markdown`` pages from **0** and ``process_pdf_with_ocr``
pages from **1**. Everything this module emits is 1-based, matching the OCR
API and the page labels readers already carry, so a page routed here is the
page that gets read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Page sources, in tier order. ``unresolved`` means no tier produced text.
PAGE_SOURCE_NATIVE = "native"
PAGE_SOURCE_LOCAL = "local"
PAGE_SOURCE_WORKER = "worker"
PAGE_SOURCE_UNRESOLVED = "unresolved"

#: ``ocr_backend`` values. The first and third are the document unit's own
#: values, unchanged. ``pdf_inspector_ocr`` names pdf-inspector's selective
#: OCR, which is not the worker. ``mixed`` is emitted when more than one
#: backend produced text: naming the highest tier instead would report
#: ``paddleocr_vl`` for a 200-page document the worker read one page of.
OCR_BACKEND_FAST_PATH = "pdf_inspector"
OCR_BACKEND_LOCAL_OCR = "pdf_inspector_ocr"
OCR_BACKEND_WORKER_PATH = "paddleocr_vl"
OCR_BACKEND_MIXED = "mixed"

#: Page source -> the backend that produced it. ``unresolved`` names none.
_SOURCE_BACKENDS = {
    PAGE_SOURCE_NATIVE: OCR_BACKEND_FAST_PATH,
    PAGE_SOURCE_LOCAL: OCR_BACKEND_LOCAL_OCR,
    PAGE_SOURCE_WORKER: OCR_BACKEND_WORKER_PATH,
}

#: Page source -> its metadata count key. The four sum to ``page_count``.
_COUNT_KEYS = {
    PAGE_SOURCE_NATIVE: "ocr_pages_native",
    PAGE_SOURCE_LOCAL: "ocr_pages_local",
    PAGE_SOURCE_WORKER: "ocr_pages_worker",
    PAGE_SOURCE_UNRESOLVED: "ocr_pages_unresolved",
}


@dataclass(frozen=True)
class PageEvidence:
    """One page's OCR evidence from a full scan.

    Attributes:
        page: 1-based page number.
        markdown: The page's native pdf-inspector Markdown, possibly empty.
        needs_ocr: Whether the scan flagged this page as needing OCR.
        reason: The scan's stated reason, when it gave one.
    """

    page: int
    markdown: str
    needs_ocr: bool
    reason: str | None


def page_evidence(file: Path) -> list[PageEvidence]:
    """Return per-page OCR evidence from a scan of every page.

    The ``page`` unit takes no sampled evidence and applies no page-fraction
    threshold: every flagged page is handled, so every page is scanned.

    Args:
        file: Path to the PDF file.

    Returns:
        One :class:`PageEvidence` per page, in page order, numbered from 1.

    Raises:
        ImportError: If ``pdf_inspector`` is not installed.
        Exception: Whatever the scan raises. The document unit can fall back
            to sampled evidence when a scan fails; the page unit cannot,
            because the scan is the only evidence it has. Swallowing the
            failure would route nothing and call the file clean.
    """
    try:
        import pdf_inspector
    except ImportError as exc:  # pragma: no cover - mirrors the adapter's message
        raise ImportError("pdf_inspector is not installed. Install with: uv sync") from exc

    scan = pdf_inspector.extract_pages_markdown(str(file))
    return [
        PageEvidence(
            # +1: the library numbers these pages from 0, the OCR API from 1.
            page=page.page + 1,
            markdown=page.markdown or "",
            needs_ocr=bool(page.needs_ocr),
            reason=getattr(page, "ocr_reason", None),
        )
        for page in scan.pages
    ]


@dataclass(frozen=True)
class PageResult:
    """One page after routing, with the tier that produced its text.

    Attributes:
        page: 1-based page number.
        text: The page's text, possibly empty.
        source: One of the ``PAGE_SOURCE_*`` values.
    """

    page: int
    text: str
    source: str


@dataclass(frozen=True)
class MergedDocument:
    """One PDF's pages merged into the document the reader emits.

    Attributes:
        text: Page texts in page order, separated by a blank line.
        counts: The four page-source counts, summing to the page count.
        ocr_backend: The one backend that produced the text, or ``mixed``.
        ocr_used: Whether OCR produced the text of at least one page.
    """

    text: str
    counts: dict[str, int]
    ocr_backend: str
    ocr_used: bool


def merge_pages(pages: list[PageResult], *, page_count: int) -> MergedDocument:
    """Merge routed pages into one document.

    Pages join in the file's order, never the order the tiers finished in,
    separated by a blank line so a heading at the top of one page does not
    fuse into the previous page's last paragraph. A page with no text
    contributes nothing rather than an empty paragraph.

    Args:
        pages: One result per page, in any order.
        page_count: The PDF's page count, used to account for pages no tier
            reported.

    Returns:
        The merged text, the four page-source counts, and the diagnostics
        that describe them.
    """
    ordered = sorted(pages, key=lambda result: result.page)
    text = "\n\n".join(result.text for result in ordered if result.text)

    counts = dict.fromkeys(_COUNT_KEYS.values(), 0)
    for result in ordered:
        counts[_COUNT_KEYS[result.source]] += 1
    # A page no tier reported is a page nothing resolved, so the four counts
    # always account for the whole document.
    reported = sum(counts.values())
    if reported < page_count:
        counts["ocr_pages_unresolved"] += page_count - reported

    # Only a page that produced text names a backend: a page nothing could
    # read is not evidence for any engine.
    backends = {
        _SOURCE_BACKENDS[result.source]
        for result in ordered
        if result.text and result.source in _SOURCE_BACKENDS
    }
    if len(backends) == 1:
        backend = next(iter(backends))
    elif backends:
        backend = OCR_BACKEND_MIXED
    else:
        # Nothing produced text. The fast path is what ran, and what the
        # document unit reports for a file it could not improve.
        backend = OCR_BACKEND_FAST_PATH
    ocr_used = bool(backends - {OCR_BACKEND_FAST_PATH})
    return MergedDocument(text=text, counts=counts, ocr_backend=backend, ocr_used=ocr_used)
