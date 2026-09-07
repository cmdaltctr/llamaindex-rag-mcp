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
from ..ocr_worker.protocol import ParseSuccess

logger = logging.getLogger(__name__)

#: ``pdf_type`` values that require OCR unconditionally (design D7.3
#: routing semantics). Anything else (notably ``text_based``) routes by
#: the calibrated thresholds only.
OCR_UNCONDITIONAL_TYPES: frozenset[str] = frozenset({"scanned", "image_based", "mixed"})

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

        Raises:
            OcrPostDispatchError: On any worker failure after the
                complete parse request was written and flushed.
            Exception: Whatever the wrapped reader raises (the existing
                reader error boundary applies unchanged).
        """
        documents = self._inner.load_data(file, *args, **kwargs)
        if not documents:
            return documents
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
