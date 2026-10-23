"""Shared, immutable PDF routing policy; no core or worker imports."""

from __future__ import annotations

#: ``pdf_type`` values that require OCR unconditionally (design D7.3
#: routing semantics). Anything else (notably ``text_based`` and
#: ``mixed``) routes by the calibrated thresholds only.
#:
#: ``mixed`` is deliberately NOT here. ``scanned`` and ``image_based``
#: both mean "the whole document is pictures", so no threshold can
#: change the answer. ``mixed`` means "some pages carry text and some do
#: not" — which is precisely the question ``ocr_fallback_page_fraction``
#: exists to answer, so routing it unconditionally skips the one check
#: designed for it. Because task 2.4 dispatches whole files with no
#: page-level stitching, that skip is multiplied by the page count.
#: See ADR-064.
#:
#: Routing and source identity share this pure-data definition.
OCR_UNCONDITIONAL_TYPES: frozenset[str] = frozenset({"scanned", "image_based"})
