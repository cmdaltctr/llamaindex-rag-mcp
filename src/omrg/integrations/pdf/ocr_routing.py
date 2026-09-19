"""OCR routing: the calibrated gate plus the seam around pdf-inspector.

Two pieces live here:

- :func:`ocr_required_by_gate` — the calibrated routing decision
  (design D7.3) as a pure function of the inspection evidence and the
  injected settings. Every threshold is configuration; this module
  contains no threshold constant.
- :class:`OcrRoutedPdfInspector` — the smallest seam the spec allows
  (task 2.3). It consumes the inspection evidence the pdf-inspector
  adapter already produced (``pdf_type``, ``pdf_confidence``, the
  scalar ``pages_needing_ocr`` count), decides fast path versus worker
  dispatch, and routes the WHOLE PDF — no page stitching (task 2.4).
  Clean text-based PDFs, including multi-column and table-heavy
  layouts, never dispatch (task 2.5): layout complexity is not a gate
  input.

Both branches stamp the additive OCR diagnostics (task 2.10):
``ocr_required``, ``ocr_used``, ``ocr_backend`` and the scalar
``pages_needing_ocr`` (the adapter already emits the count — never the
page list, which no vector store accepts).

Failure behaviour follows design "Failure behaviour" 2/4/5 exactly:

- worker unavailable BEFORE dispatch → keep the partial pdf-inspector
  Markdown, stamp the degraded diagnostics, log an actionable message,
  continue the batch (task 2.7);
- worker failure AFTER dispatch → raise :class:`OcrPostDispatchError`
  so the existing per-file reader error boundary reports the file
  failed without substituting the partial Markdown (task 2.9).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..ocr_worker.client import OcrWorkerError
from ..ocr_worker.protocol import PAGES_PROTOCOL_VERSION, ParseSuccess
from .ocr_policy import OCR_UNCONDITIONAL_TYPES
from .page_routing import (
    PAGE_SOURCE_LOCAL,
    PAGE_SOURCE_NATIVE,
    PAGE_SOURCE_UNRESOLVED,
    PAGE_SOURCE_WORKER,
    LocalOcrPage,
    PageEvidence,
    PageResult,
    local_ocr,
    merge_pages,
    page_evidence,
)

logger = logging.getLogger(__name__)

#: Diagnostic backend identifiers (task 2.10). The fast path and the
#: degraded path both ran pdf-inspector alone; only the worker path
#: may claim the isolated backend.
OCR_BACKEND_FAST_PATH = "pdf_inspector"
OCR_BACKEND_WORKER_PATH = "paddleocr_vl"


class OcrPostDispatchError(RuntimeError):
    """A worker failure after a complete request was written and flushed.

    Attributes:
        code: The structured worker failure code (``timeout``,
            ``worker_crashed``, ``worker_closed_output``,
            ``protocol_violation``, or a worker-reported code).
        message: Human-readable description for the per-file error.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"ocr_worker.{code}: {message}")
        self.code = code
        self.message = message


def _stamp_ocr_diagnostics(
    metadata: dict[str, Any],
    *,
    ocr_required: bool,
    ocr_used: bool,
    ocr_backend: str,
) -> None:
    """Stamp the four additive OCR diagnostic keys (task 2.10).

    ``pages_needing_ocr`` is already present as a scalar count from the
    pdf-inspector adapter; the other three are additive and never
    overwrite more authoritative existing values.
    """
    metadata["ocr_required"] = ocr_required
    metadata["ocr_used"] = ocr_used
    metadata["ocr_backend"] = ocr_backend


class OcrRoutedPdfInspector:
    """Routing seam around one pdf-inspector reader instance.

    Transparent to the reader registry: constructed by
    :func:`integrations.pdf.factory.build_pdf_reader` only when the
    resolved reader is ``pdf_inspector`` AND the operator enabled the
    OCR fallback. Everything else — the declared ``text_format``, the
    ``load_data`` contract — is the wrapped reader's.
    """

    def __init__(self, inner: Any, *, settings: Any, ocr_client: Any = None) -> None:
        """Wrap *inner* with the routing decision from injected settings.

        Args:
            inner: The concrete pdf-inspector reader instance.
            settings: Injected settings carrying the routing gate and
                the worker request timeout.
            ocr_client: Injected managed OCR worker client (engine- or
                operation-owned). ``None`` means no worker is wired —
                OCR-required files degrade deterministically.
        """
        self._inner = inner
        self._settings = settings
        self._ocr_client = ocr_client

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        """Read one PDF, routing it through the OCR gate.

        Args:
            file: Path to the PDF file.
            *args: Forwarded to the wrapped reader.
            **kwargs: Forwarded to the wrapped reader.

        Returns:
            The pdf-inspector documents (fast or degraded path) or a
            document built from the worker's structured Markdown
            (worker path), always carrying the four OCR diagnostics.
            Under the ``page`` routing unit, one document whose pages
            were read by the highest tier that produced text for them,
            carrying the four page-source counts.

        Raises:
            OcrPostDispatchError: On any worker failure after the
                complete parse request was written and flushed.
            Exception: Whatever the wrapped reader raises (the existing
                reader error boundary applies unchanged).
        """
        documents = self._inner.load_data(file, *args, **kwargs)
        if not documents:
            return documents
        if getattr(self._settings, "ocr_routing_unit", "document") == "page":
            return self._page_unit_documents(file, documents[0])
        evidence = documents[0].metadata
        required = ocr_required_by_gate(
            pdf_type=str(evidence.get("pdf_type", "")),
            pdf_confidence=float(evidence.get("pdf_confidence", 1.0)),
            pages_needing_ocr=int(evidence.get("pages_needing_ocr", 0)),
            page_count=int(evidence.get("page_count", 0)),
            settings=self._settings,
        )
        if not required:
            _stamp_ocr_diagnostics(
                evidence,
                ocr_required=False,
                ocr_used=False,
                ocr_backend=OCR_BACKEND_FAST_PATH,
            )
            return documents

        client = self._ocr_client
        if client is None or not client.fingerprint.available:
            _stamp_ocr_diagnostics(
                evidence,
                ocr_required=True,
                ocr_used=False,
                ocr_backend=OCR_BACKEND_FAST_PATH,
            )
            pdf_type = evidence.get("pdf_type", "")
            logger.warning(
                "OCR required for %s (pdf_type=%s, %s page(s) flagged) but the "
                "isolated worker is unavailable — keeping the partial "
                "pdf-inspector extraction. Provision the worker environment "
                "and set OCR_WORKER_COMMAND to enable document understanding.",
                getattr(file, "name", file),
                pdf_type,
                "classification-flagged"
                if pdf_type in OCR_UNCONDITIONAL_TYPES
                else "threshold-flagged",
            )
            return documents

        try:
            result = client.parse(str(file))
        except OcrWorkerError as exc:
            raise OcrPostDispatchError(exc.code, exc.message) from exc
        return self._worker_document(evidence, result)

    def _worker_document(self, evidence: dict[str, Any], result: ParseSuccess) -> list:
        """Build the worker-path document, preserving provenance metadata."""
        from llama_index.core import Document

        merged = dict(evidence)
        _stamp_ocr_diagnostics(
            merged,
            ocr_required=True,
            ocr_used=True,
            ocr_backend=OCR_BACKEND_WORKER_PATH,
        )
        return [Document(text=result.markdown, metadata=merged)]

    # ── The page routing unit (tasks 4.4, 4.5c, 4.6) ──────────────────

    def _page_unit_documents(self, file: Path, inner_document: Any) -> list:
        """Read one PDF page by page and merge the tiers into one document.

        The full scan is the only evidence (task 4.1): every flagged page
        is OCRed locally (task 4.2), the pages the post-check rejects go
        to the worker in ONE request (task 4.4), and the merge joins the
        pages back in order (task 4.5c). Degradation never fails the file
        (task 4.6): a missing local runtime keeps native text, a missing
        or unattributable worker keeps the best available text, and both
        count the affected pages unresolved. Only a worker failure AFTER
        a complete request was flushed raises, exactly as the document
        unit's post-dispatch boundary does.

        Args:
            file: Path to the PDF file.
            inner_document: The wrapped reader's document; its metadata
                is the base the counts and diagnostics join.

        Returns:
            A one-document list carrying the merged text, the four
            page-source counts and the OCR diagnostics.

        Raises:
            OcrPostDispatchError: On a worker failure after dispatch.
            Exception: Whatever the full scan raises — the page unit has
                no sampled evidence to fall back to.
        """
        from llama_index.core import Document

        evidence = page_evidence(file)
        page_count = len(evidence)
        flagged = {entry.page for entry in evidence if entry.needs_ocr}

        results: list[PageResult] = []
        placed: set[int] = set()
        escalated: dict[int, LocalOcrPage] = {}
        if flagged:
            try:
                local_pages = local_ocr(file, sorted(flagged), settings=self._settings)
            except Exception as exc:  # noqa: BLE001 - a missing runtime degrades, never fails
                logger.warning(
                    "Local OCR tier unavailable for %s (%s: %s); %d flagged page(s) "
                    "keep native text and count unresolved",
                    getattr(file, "name", file),
                    type(exc).__name__,
                    exc,
                    len(flagged),
                )
            else:
                for page in local_pages:
                    if page.escalates:
                        escalated[page.page] = page
                    else:
                        results.append(
                            PageResult(page=page.page, text=page.text, source=PAGE_SOURCE_LOCAL)
                        )
                        placed.add(page.page)

        worker_text = self._escalated_worker_text(file, sorted(escalated)) if escalated else {}

        for entry in evidence:
            if entry.page in placed:
                continue
            if entry.page in escalated:
                text = worker_text.get(entry.page, "")
                if text:
                    results.append(
                        PageResult(page=entry.page, text=text, source=PAGE_SOURCE_WORKER)
                    )
                else:
                    # The escalation did not resolve this page: the worker
                    # was missing, unattributable, or returned nothing. The
                    # best available text is kept; no marker is inserted.
                    results.append(
                        PageResult(
                            page=entry.page,
                            text=self._fallback_text(escalated[entry.page], entry),
                            source=PAGE_SOURCE_UNRESOLVED,
                        )
                    )
            elif entry.page in flagged:
                # The local tier never ran; native text is all there is.
                results.append(
                    PageResult(page=entry.page, text=entry.markdown, source=PAGE_SOURCE_UNRESOLVED)
                )
            else:
                results.append(
                    PageResult(page=entry.page, text=entry.markdown, source=PAGE_SOURCE_NATIVE)
                )

        merged = merge_pages(results, page_count=page_count)
        metadata = dict(inner_document.metadata)
        metadata["page_count"] = page_count
        # The complete scan is the page unit's authority on the count.
        metadata["pages_needing_ocr"] = len(flagged)
        _stamp_ocr_diagnostics(
            metadata,
            ocr_required=bool(flagged),
            ocr_used=merged.ocr_used,
            ocr_backend=merged.ocr_backend,
        )
        metadata.update(merged.counts)

        if not merged.text and inner_document.text:
            # ADR-066 rescue of last resort: the scan produced no text on
            # any page, yet the wrapped reader recovered the document
            # through the fallback chain. That rescued text is the record;
            # the counts report every page native, the same whole-document
            # claim the document unit makes for a rescued file, with
            # ``extraction_fallback_backend`` naming the true origin.
            metadata.update(
                {
                    "ocr_pages_native": page_count,
                    "ocr_pages_local": 0,
                    "ocr_pages_worker": 0,
                    "ocr_pages_unresolved": 0,
                }
            )
            _stamp_ocr_diagnostics(
                metadata,
                ocr_required=bool(flagged),
                ocr_used=False,
                ocr_backend=OCR_BACKEND_FAST_PATH,
            )
            return [Document(text=inner_document.text, metadata=metadata)]
        return [Document(text=merged.text, metadata=metadata)]

    def _escalated_worker_text(self, file: Path, pages: list[int]) -> dict[int, str]:
        """Dispatch the escalated pages in one request and attribute per page.

        Args:
            file: Path to the PDF file.
            pages: 1-based escalated page numbers, sorted.

        Returns:
            Page number to worker Markdown. An empty dict means the
            escalation degraded: the worker is unavailable, cannot serve
            page-listed requests (it speaks a protocol older than
            ``PAGES_PROTOCOL_VERSION``), or its response cannot be
            attributed per page. All three keep the best available text
            and count the pages unresolved.

        Raises:
            OcrPostDispatchError: On a worker failure after the complete
                request was written and flushed — the same boundary the
                document unit applies.
        """
        name = getattr(file, "name", file)
        client = self._ocr_client
        if client is None or not client.fingerprint.available:
            logger.warning(
                "%d escalated page(s) in %s have no isolated worker; keeping the "
                "best available text and counting them unresolved. Provision the "
                "worker environment and set OCR_WORKER_COMMAND to enable it.",
                len(pages),
                name,
            )
            return {}
        if client.fingerprint.protocol_version != PAGES_PROTOCOL_VERSION:
            # A worker still on 1.0 during a rolling upgrade must never
            # receive a page-listed request: it would reject the 1.1
            # envelope after dispatch and fail the file. A worker that
            # cannot speak pages is, for page routing, a worker that is
            # not there — degrade, never fail the file.
            logger.warning(
                "%d escalated page(s) in %s need a worker that speaks protocol "
                "%s, but this worker speaks %s; page routing degrades and the "
                "pages keep their best available text, counting unresolved. "
                "Upgrade the worker to enable page-listed parsing.",
                len(pages),
                name,
                PAGES_PROTOCOL_VERSION,
                client.fingerprint.protocol_version,
            )
            return {}
        try:
            result = client.parse(str(file), pages=pages)
        except OcrWorkerError as exc:
            raise OcrPostDispatchError(exc.code, exc.message) from exc
        pages_markdown = result.pages_markdown
        if pages_markdown is None or len(pages_markdown) != len(pages):
            logger.warning(
                "Worker response for %s cannot be attributed per page (pages_markdown "
                "absent or not parallel to the request); escalated pages keep their "
                "best available text and count unresolved",
                name,
            )
            return {}
        return dict(zip(pages, pages_markdown, strict=True))

    @staticmethod
    def _fallback_text(local_page: LocalOcrPage, entry: PageEvidence) -> str:
        """Return the best text an unresolved escalated page can carry."""
        if local_page.text:
            return local_page.text
        return entry.markdown


def ocr_required_by_gate(
    *,
    pdf_type: str,
    pdf_confidence: float,
    pages_needing_ocr: int,
    page_count: int,
    settings: Any,
) -> bool:
    """Decide whether inspection evidence routes a PDF to the OCR worker.

    Reads every threshold from the injected settings object (spec
    pdf-reader: "Routing threshold is read from injected settings" —
    this module contains no threshold constant). A ``0.0`` threshold is
    the packaged "never additionally triggered" sentinel, so at the
    defaults the decision is classification-only.

    Args:
        pdf_type: ``pdf-inspector`` classification of the PDF.
        pdf_confidence: ``pdf-inspector`` classification confidence.
        pages_needing_ocr: Count of pages the classifier flagged as
            needing OCR (the scalar evidence, not the page list).
        page_count: Total page count of the PDF.
        settings: Injected settings carrying ``ocr_fallback_min_confidence``
            and ``ocr_fallback_page_fraction``.

    Returns:
        True when the PDF is OCR-required under the injected gate.
    """
    if pdf_type in OCR_UNCONDITIONAL_TYPES:
        return True
    min_confidence = settings.ocr_fallback_min_confidence
    # 0.0 is the disabled sentinel: a confidence can never be negative,
    # so a bare `confidence < 0.0` comparison would never fire anyway,
    # but the explicit guard keeps the sentinel semantics readable and
    # protects a future negative-confidence classifier from routing
    # every document at the packaged default.
    if min_confidence > 0.0 and pdf_confidence < min_confidence:
        return True
    fraction = settings.ocr_fallback_page_fraction
    # 0.0 is the disabled sentinel: `0/1 >= 0.0` is always true, so a
    # bare comparison would route every text-based PDF at the packaged
    # default — the opposite of classification-only routing.
    if fraction > 0.0 and page_count > 0 and (pages_needing_ocr / page_count) >= fraction:
        return True
    return False
