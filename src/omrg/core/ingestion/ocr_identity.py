"""Canonical OCR identity payload builders (task 2.13, design D8).

Two small pure builders produce the OCR corner of the
``source_index_identity`` payload. They live beside
``core/ingestion/source_state.py`` rather than inside it because that
module sits at the 500-line ceiling; ``source_state`` imports them the
same way ``compose`` re-imports from ``capabilities`` when the natural
home is full.

Design D8 contract implemented here:

- the OCR routing gate's three configured values (``enabled``,
  ``min_confidence``, ``page_fraction``) and the unconditional routing
  types enter the payload as resolved data, never re-read from the
  environment;
- the resolved worker fingerprint enters as ONE canonical,
  transient-free payload. An unavailable worker contributes the stable
  ``UNAVAILABLE_OCR_WORKER_FINGERPRINT`` shape — the field is never
  omitted and never carries process identifiers, timestamps, or host
  paths;
- no second identity mechanism and no hashing outside
  ``build_index_identity``: these builders return plain JSON-ready
  dictionaries and the single sha256 stays in ``source_state``.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

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
#: This constant lives in the identity module (not in
#: ``integrations/pdf/ocr_routing.py``) because it is identity-relevant:
#: changing which types route unconditionally changes the routing
#: decision for affected PDFs, so it MUST participate in the index
#: identity to prevent stale ``skipped_unchanged`` results. The routing
#: module imports and re-exports it so existing imports keep working.
OCR_UNCONDITIONAL_TYPES: frozenset[str] = frozenset({"scanned", "image_based"})

#: The canonical unavailable fingerprint payload. Byte-identical, by
#: construction, to ``asdict(UNAVAILABLE_OCR_WORKER_FINGERPRINT)`` from
#: ``integrations/ocr_worker/fingerprint.py``: every identity field
#: empty and ``available=False``. Duplicated here only so this leaf
#: module needs no import from ``integrations/``; the re-ingestion
#: tests pin the no-drift equality.
_UNAVAILABLE_FINGERPRINT_PAYLOAD: dict[str, Any] = {
    "available": False,
    "protocol_version": "",
    "packages": (),
    "pipeline_identity": "",
    "pipeline_revision": "",
    "model_identity": "",
    "model_revision": "",
    "output_schema_id": "",
    "output_schema_version": "",
}


def ocr_routing_payload(settings: Any) -> dict[str, Any]:
    """Return the canonical OCR routing-gate payload from settings.

    Args:
        settings: Settings object (flat ``Settings`` or frozen
            ``EffectiveSettings``) carrying the three top-level routing
            fields ``ocr_fallback_enabled``,
            ``ocr_fallback_min_confidence``, and
            ``ocr_fallback_page_fraction``.

    Returns:
        A JSON-ready dict with the three calibrated gate values that
        decide routing (design D7.3) plus the unconditional routing
        types. The operational worker settings (command, environment,
        timeout) are deliberately absent: they shape dispatch, never
        chunk text. The unconditional types are included because
        changing which ``pdf_type`` values bypass the thresholds changes
        the routing decision for affected PDFs, and the index identity
        must reflect that to prevent stale ``skipped_unchanged`` results.
    """
    return {
        "enabled": settings.ocr_fallback_enabled,
        "min_confidence": settings.ocr_fallback_min_confidence,
        "page_fraction": settings.ocr_fallback_page_fraction,
        "unconditional_types": sorted(OCR_UNCONDITIONAL_TYPES),
    }


def ocr_fingerprint_payload(fingerprint: Any) -> dict[str, Any]:
    """Return the canonical transient-free payload of a resolved fingerprint.

    Args:
        fingerprint: The resolved :class:`OcrWorkerFingerprint` (any
            frozen dataclass with its field set), or ``None`` when no
            fingerprint was supplied.

    Returns:
        ``asdict(fingerprint)`` for a dataclass — the canonical shape
        carries availability, protocol version, package
        name/version pairs, pipeline and model identities and
        revisions, and the output-schema identity and version. Any
        other input (including ``None``) yields the stable unavailable
        payload, so a missing fingerprint can never silently omit the
        field from the index identity.
    """
    if is_dataclass(fingerprint):
        return asdict(fingerprint)
    return dict(_UNAVAILABLE_FINGERPRINT_PAYLOAD)
