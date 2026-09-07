"""OCR routing gate — the calibrated evidence expressed as injected settings.

Design D7.3 of change improve-rag-input-quality-5: the threshold that
selects the OCR fallback is injected configuration (top-level
``EffectiveSettings`` fields beside ``pdf_reader``), never a constant
here. The packaged defaults keep the fallback off entirely; the 0.0
threshold defaults mean classification-only routing so no text-based
PDF is rerouted until an operator supplies calibrated values.

The gate consumes only the inspection evidence ``pdf-inspector``
already produced (design D1): ``pdf_type``, ``pdf_confidence`` and the
``pages_needing_ocr`` count. Layout complexity is deliberately absent
as an input — a multi-column or table-heavy text-based PDF that
pdf-inspector extracts acceptably must stay on the fast path (task
2.5).
"""

from __future__ import annotations

from typing import Any

#: ``pdf_type`` values that require OCR unconditionally (design D7.3
#: routing semantics). Anything else (notably ``text_based``) routes by
#: the calibrated thresholds only.
OCR_UNCONDITIONAL_TYPES: frozenset[str] = frozenset({"scanned", "image_based", "mixed"})


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
