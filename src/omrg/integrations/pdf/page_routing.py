"""Page-unit OCR routing for the pdf-inspector path (change page-level-ocr-routing).

``OCR_ROUTING_UNIT=page`` routes a PDF page by page instead of whole. This
module holds that unit's logic, so the document unit's seam in
``ocr_routing.py`` stays the shape it has always been: per-page evidence
from a full scan, the local OCR tier with its post-check escalation
(tasks 4.2 and 4.2a), and the merge back into one document.

Page numbering is the trap here. pdf-inspector numbers
``extract_pages_markdown`` pages from **0** and ``process_pdf_with_ocr``
pages from **1**. Everything this module emits is 1-based, matching the OCR
API and the page labels readers already carry, so a page routed here is the
page that gets read.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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
class LocalOcrPage:
    """One flagged page after the local OCR tier, with its escalation verdict.

    Attributes:
        page: 1-based page number.
        text: The page's local OCR Markdown, possibly empty.
        confidence: The engine's reported OCR confidence, ``None`` when it
            reported none.
        model: The resolved local model identity (``name@revision``),
            ``None`` when the engine named no model.
        escalates: Whether the post-check sends this page to the worker.
        reasons: Every escalation condition that fired, in check order.
    """

    page: int
    text: str
    confidence: float | None
    model: str | None
    escalates: bool
    reasons: tuple[str, ...]


def _model_identity(provenance: Any) -> str | None:
    """Return ``name@revision`` from a page's provenance, or ``None``."""
    model = getattr(provenance, "ocr_model", None)
    if model is None:
        return None
    return f"{model.name}@{model.revision}"


def local_ocr(file: Path, pages: list[int], *, settings: Any) -> list[LocalOcrPage]:
    """OCR every flagged page locally with pdf-inspector's selective OCR.

    Tier 1 of the ``page`` unit (design decision 3): ``force`` mode with the
    1-based page list, so the library re-routes nothing — exactly the call
    Experiment 33 task 6.7 measured. The model directory and offline mode
    come from the injected settings; an empty directory means the library's
    default cache.

    The engine's own ``minimum_confidence`` and
    ``hosted_recommendation_confidence`` parameters stay at their library
    defaults: the experiment measured those defaults and applies the cut in
    the post-check below. Feeding our threshold into the engine would run
    unmeasured behaviour.

    Args:
        file: Path to the PDF file.
        pages: 1-based page numbers to OCR. Uniqueness and order are the
            caller's to guarantee; the evidence scan emits sorted uniques.
        settings: Injected settings carrying ``ocr_local_model_directory``,
            ``ocr_local_offline`` and ``ocr_local_min_confidence``.

    Returns:
        One :class:`LocalOcrPage` per requested page, in page order.

    Raises:
        ImportError: If ``pdf_inspector`` is not installed.
        Exception: Whatever the engine raises. Degradation for a missing
            runtime is the caller's (task 4.6); the tier reports.
    """
    if not pages:
        return []
    try:
        import pdf_inspector
    except ImportError as exc:  # pragma: no cover - mirrors the adapter's message
        raise ImportError("pdf_inspector is not installed. Install with: uv sync") from exc

    result = pdf_inspector.process_pdf_with_ocr(
        str(file),
        mode="force",
        page_numbers=sorted(pages),
        model_directory=(settings.ocr_local_model_directory or None),
        offline=bool(settings.ocr_local_offline),
    )
    by_number = {page.page_number: page for page in result.pages}
    minimum = settings.ocr_local_min_confidence
    outcomes: list[LocalOcrPage] = []
    for number in sorted(pages):
        page = by_number.get(number)
        provenance = getattr(page, "provenance", None) if page is not None else None
        text = (getattr(page, "markdown", "") or "") if page is not None else ""
        confidence = getattr(provenance, "ocr_confidence", None)
        # Post-check escalation (design decision 4), decided AFTER the
        # attempt: a pre-check would need a signal nobody has measured.
        reasons: list[str] = []
        if page is None:
            reasons.append("missing_page")
        if not text.strip():
            reasons.append("empty_text")
        # ``None`` escalates with the below-threshold pages: an unreported
        # confidence cannot vouch for the text, and the experiment's
        # calibration treated it as zero.
        if confidence is None or confidence < minimum:
            reasons.append("low_confidence")
        if bool(getattr(provenance, "hosted_recommended", False)):
            reasons.append("hosted_recommended")
        outcomes.append(
            LocalOcrPage(
                page=number,
                text=text,
                confidence=confidence,
                model=_model_identity(provenance),
                escalates=bool(reasons),
                reasons=tuple(reasons),
            )
        )
    return outcomes


# ── The local model resolution probe (task 4.2, identity) ─────────────────

_RESOLUTION_LOCK = threading.Lock()
#: Process-wide cache of resolved local model identities, keyed by the
#: ``(model_directory, offline)`` pair the probe ran under — the pair
#: ``local_ocr`` feeds the engine, so a different pair is a different
#: model and must resolve afresh. Only successful identities are cached:
#: an unresolved runtime is re-probed, so the identity is gained the
#: moment the runtime appears and the index identity follows.
_local_model_resolution: dict[tuple[str, bool], str] = {}


def reset_local_model_resolution() -> None:
    """Clear the cached local model resolution.

    Test seam, matching the reranker's ``reset_model_cache`` contract: the
    cache is process state, and a test that stubs the engine needs to start
    from a blank slate and leave one behind.
    """
    with _RESOLUTION_LOCK:
        _local_model_resolution.clear()


def resolve_local_model_identity(settings: Any) -> str | None:
    """Resolve the local OCR model's ``name@revision``, once per settings pair.

    pdf-inspector reports the identity only in per-page provenance after
    OCR runs, and an empty page list skips the model entirely, so the
    resolution is a one-page ``force`` attempt on a generated blank PDF.
    The blank page costs one render and no recognition work; its
    provenance still names the model. The probe applies the same model
    directory and offline settings as the tier, so it resolves the model
    the tier would use, and the cache is keyed by exactly that pair.

    A successful resolution is cached per ``(model_directory, offline)``.
    A failure resolves to ``None`` and caches nothing: an unavailable
    runtime is re-probed on the next call, so the identity is gained when
    the runtime appears — reindexing exactly when the emitted text would
    change, which a cached ``None`` would miss. Lock-guarded because
    ingest operations run on worker threads.

    Args:
        settings: Injected settings carrying ``ocr_local_model_directory``
            and ``ocr_local_offline``.

    Returns:
        The resolved ``name@revision``, or ``None`` when unresolvable.
    """
    key = ((settings.ocr_local_model_directory or ""), bool(settings.ocr_local_offline))
    with _RESOLUTION_LOCK:
        cached = _local_model_resolution.get(key)
        if cached is not None:
            return cached
        identity = _probe_local_model_identity(settings)
        if identity is not None:
            _local_model_resolution[key] = identity
        return identity


def _probe_local_model_identity(settings: Any) -> str | None:
    """Run the one-page blank probe and read the model identity it reports."""
    path: str | None = None
    try:
        import pdf_inspector
        from pypdf import PdfWriter

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            path = handle.name
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(path)
        result = pdf_inspector.process_pdf_with_ocr(
            path,
            mode="force",
            page_numbers=[1],
            model_directory=(settings.ocr_local_model_directory or None),
            offline=bool(settings.ocr_local_offline),
        )
        for page in result.pages:
            identity = _model_identity(getattr(page, "provenance", None))
            if identity is not None:
                return identity
        return None
    except Exception as exc:  # noqa: BLE001 - an unresolvable runtime is a None, not a failure
        logger.warning(
            "Local OCR model identity unresolved (%s: %s); the index identity "
            "omits the model until the local OCR runtime is available",
            type(exc).__name__,
            exc,
        )
        return None
    finally:
        if path is not None:
            try:
                os.unlink(path)
            except OSError:  # pragma: no cover - best-effort temp cleanup
                pass


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
