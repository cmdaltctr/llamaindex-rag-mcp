"""Gate-semantics unit tests for the OCR routing decision (task 1.8/2.3).

Pure-function coverage of design D7.3: classification-only routing at
the packaged 0.0/0.0 defaults, the confidence and fraction triggers as
specified, and the calibrated-gate negative for a clean text-based
PDF. Thresholds always arrive through the injected settings — never a
module constant.
"""

from __future__ import annotations

from omrg.integrations.pdf.ocr_routing import OCR_UNCONDITIONAL_TYPES, ocr_required_by_gate

# ── Classification-only routing at the packaged defaults ───────────────────


def test_text_based_never_routes_at_default_thresholds(effective_settings) -> None:
    """0.0/0.0 means classification-only: low confidence alone is inert."""
    settings = effective_settings()
    assert (
        ocr_required_by_gate(
            pdf_type="text_based",
            pdf_confidence=0.1,
            pages_needing_ocr=0,
            page_count=3,
            settings=settings,
        )
        is False
    )


def test_zero_confidence_with_zero_threshold_does_not_route(effective_settings) -> None:
    """The 0.0 sentinel is disabled, not 'below everything'."""
    settings = effective_settings()
    assert (
        ocr_required_by_gate(
            pdf_type="text_based",
            pdf_confidence=0.0,
            pages_needing_ocr=0,
            page_count=1,
            settings=settings,
        )
        is False
    )


def test_all_ocr_pages_with_zero_fraction_does_not_route(effective_settings) -> None:
    """The 0.0 fraction sentinel is disabled even when every page is flagged."""
    settings = effective_settings()
    assert (
        ocr_required_by_gate(
            pdf_type="text_based",
            pdf_confidence=1.0,
            pages_needing_ocr=2,
            page_count=2,
            settings=settings,
        )
        is False
    )


def test_unconditional_types_route_even_at_defaults(effective_settings) -> None:
    """scanned / image-based / mixed are OCR-required unconditionally."""
    settings = effective_settings()
    for pdf_type in sorted(OCR_UNCONDITIONAL_TYPES):
        assert (
            ocr_required_by_gate(
                pdf_type=pdf_type,
                pdf_confidence=1.0,
                pages_needing_ocr=0,
                page_count=1,
                settings=settings,
            )
            is True
        ), pdf_type


def test_mixed_is_not_unconditional(effective_settings) -> None:
    """``mixed`` routes by the thresholds, never unconditionally (ADR-064).

    A ``mixed`` classification means some pages carry text and some do
    not — the exact question ``ocr_fallback_page_fraction`` answers.
    Routing it unconditionally skipped that check, and whole-file
    dispatch multiplied the skip by the page count.
    """
    assert "mixed" not in OCR_UNCONDITIONAL_TYPES


def test_mixed_with_few_flagged_pages_stays_on_the_fast_path(effective_settings) -> None:
    """The experiment 28 regression: 10 flagged pages must not route 991.

    Shaped from the real document that failed experiment 28's safety
    gate — ``mixed`` at confidence 0.76, 991 pages, 10 flagged, 1,127
    characters per page. Under the calibrated gate the flagged fraction
    is 1%, far below the 0.5 trigger, so it belongs on the fast path.
    """
    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_fallback_min_confidence=0.5,
        ocr_fallback_page_fraction=0.5,
    )
    assert (
        ocr_required_by_gate(
            pdf_type="mixed",
            pdf_confidence=0.7625,
            pages_needing_ocr=10,
            page_count=991,
            settings=settings,
        )
        is False
    )


def test_mixed_with_material_flagged_pages_still_routes(effective_settings) -> None:
    """Demoting ``mixed`` must not stop a genuinely OCR-needing mixed PDF.

    Above the calibrated page fraction the same classification routes,
    so the fix narrows the rule without disabling it.
    """
    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_fallback_min_confidence=0.5,
        ocr_fallback_page_fraction=0.5,
    )
    assert (
        ocr_required_by_gate(
            pdf_type="mixed",
            pdf_confidence=0.9,
            pages_needing_ocr=6,
            page_count=10,
            settings=settings,
        )
        is True
    )


def test_mixed_with_low_confidence_still_routes(effective_settings) -> None:
    """A poorly-classified mixed PDF still reaches OCR via the confidence floor."""
    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_fallback_min_confidence=0.5,
        ocr_fallback_page_fraction=0.5,
    )
    assert (
        ocr_required_by_gate(
            pdf_type="mixed",
            pdf_confidence=0.3,
            pages_needing_ocr=0,
            page_count=20,
            settings=settings,
        )
        is True
    )


def test_unknown_classification_routes_by_thresholds_only(effective_settings) -> None:
    """An unseen classification value falls through to the calibrated path."""
    settings = effective_settings()
    assert (
        ocr_required_by_gate(
            pdf_type="something_new",
            pdf_confidence=1.0,
            pages_needing_ocr=0,
            page_count=1,
            settings=settings,
        )
        is False
    )


# ── Confidence trigger ─────────────────────────────────────────────────────


def test_confidence_trigger_fires_strictly_below_threshold(effective_settings) -> None:
    """Confidence strictly below the threshold routes; equal does not."""
    settings = effective_settings(ocr_fallback_min_confidence=0.5)
    below = ocr_required_by_gate(
        pdf_type="text_based",
        pdf_confidence=0.49,
        pages_needing_ocr=0,
        page_count=1,
        settings=settings,
    )
    equal = ocr_required_by_gate(
        pdf_type="text_based",
        pdf_confidence=0.5,
        pages_needing_ocr=0,
        page_count=1,
        settings=settings,
    )
    assert below is True
    assert equal is False


# ── Fraction trigger ───────────────────────────────────────────────────────


def test_fraction_trigger_fires_at_or_above_threshold(effective_settings) -> None:
    """pages_needing_ocr/page_count at or above the fraction routes."""
    settings = effective_settings(ocr_fallback_page_fraction=0.5)
    at_threshold = ocr_required_by_gate(
        pdf_type="text_based",
        pdf_confidence=1.0,
        pages_needing_ocr=1,
        page_count=2,
        settings=settings,
    )
    below_threshold = ocr_required_by_gate(
        pdf_type="text_based",
        pdf_confidence=1.0,
        pages_needing_ocr=1,
        page_count=3,
        settings=settings,
    )
    assert at_threshold is True
    assert below_threshold is False


def test_fraction_trigger_is_inert_with_zero_flagged_pages(effective_settings) -> None:
    """No flagged pages means no fraction trigger however the gate is set."""
    settings = effective_settings(ocr_fallback_page_fraction=0.5)
    assert (
        ocr_required_by_gate(
            pdf_type="text_based",
            pdf_confidence=1.0,
            pages_needing_ocr=0,
            page_count=4,
            settings=settings,
        )
        is False
    )


# ── The calibrated-gate negative (task 1.7 gate, spec scenario) ────────────


def test_clean_text_pdf_never_routes_at_calibrated_gate(effective_settings) -> None:
    """A text-based PDF at confidence 1.0 with 0 OCR pages stays on pdf-inspector.

    This is the calibration fixture baseline (cal_clean_text.pdf /
    cal_table_text.pdf) evaluated at a representative calibrated gate
    (0.5/0.5): layout complexity alone must never select OCR (task
    2.5, spec scenario "Complex text layout does not imply OCR").
    """
    settings = effective_settings(
        ocr_fallback_min_confidence=0.5,
        ocr_fallback_page_fraction=0.5,
    )
    assert (
        ocr_required_by_gate(
            pdf_type="text_based",
            pdf_confidence=1.0,
            pages_needing_ocr=0,
            page_count=1,
            settings=settings,
        )
        is False
    )


def test_thresholds_come_from_injected_settings(effective_settings) -> None:
    """The same evidence routes differently under different injected gates.

    Proves the decision follows the injected settings object (spec
    scenario "Routing threshold is read from injected settings") — no
    hardcoded threshold can produce this pair of outcomes.
    """
    strict_off = effective_settings()
    strict_on = effective_settings(ocr_fallback_min_confidence=0.95)
    evidence = dict(
        pdf_type="text_based",
        pdf_confidence=0.9,
        pages_needing_ocr=0,
        page_count=1,
    )
    assert ocr_required_by_gate(settings=strict_off, **evidence) is False
    assert ocr_required_by_gate(settings=strict_on, **evidence) is True
