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
- the identity carries what changes the emitted text — the routing unit
  and the local tier's escalation threshold — and not where files live or
  how they are fetched. A model directory is a filesystem location, so the
  same model under a different path would reindex for nothing. Offline
  mode decides whether a download may happen; its only route to different
  text is whether the model resolves, which the resolved model identity
  records directly (change page-level-ocr-routing, task 4.2);
- the routing-unit keys are present only when the unit is not
  ``document``, so an install on the default emits the payload it emits
  today and no source reindexes. Absence of ``routing_unit`` means
  ``document``: no other configuration emits that key. The same rule
  scopes ``local_tier.model``: it joins only with a resolved identity on
  a ``page``-unit install, where the model's text can differ. Absence
  means unresolved, which is itself identity-relevant — the runtime
  appearing changes the emitted text, so the digest moves then and only
  then;
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

from ...integrations.pdf.ocr_policy import OCR_UNCONDITIONAL_TYPES

#: The canonical unavailable fingerprint payload. Byte-identical, by
#: construction, to ``asdict(UNAVAILABLE_OCR_WORKER_FINGERPRINT)`` from
#: ``integrations/ocr_worker/fingerprint.py``: every identity field
#: empty and ``available=False``. Duplicated here only so this leaf
#: module does not import the worker implementation; the re-ingestion
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


def ocr_routing_payload(
    settings: Any, *, local_model_identity: str | None = None
) -> dict[str, Any]:
    """Return the canonical OCR routing-gate payload from settings.

    Args:
        settings: Settings object (flat ``Settings`` or frozen
            ``EffectiveSettings``) carrying the three top-level routing
            fields ``ocr_fallback_enabled``,
            ``ocr_fallback_min_confidence``, and
            ``ocr_fallback_page_fraction``.
        local_model_identity: The local OCR tier's resolved model
            identity (``name@revision``), or ``None`` when unresolved.
            Recorded only under a non-``document`` unit: a document-unit
            install has no local tier, so a resolved identity passed for
            one is dropped rather than hashed.

    Returns:
        A JSON-ready dict with the three calibrated gate values that
        decide routing (design D7.3) plus the unconditional routing
        types, and — only when the routing unit is not ``document`` —
        that unit, the local tier's escalation threshold, and, when
        resolved, the local model identity. The operational worker
        settings (command, environment, timeout) are deliberately
        absent: they shape dispatch, never chunk text. The unconditional
        types are included because changing which ``pdf_type`` values
        bypass the thresholds changes the routing decision for affected
        PDFs, and the index identity must reflect that to prevent stale
        ``skipped_unchanged`` results.
    """
    payload = {
        "enabled": settings.ocr_fallback_enabled,
        "min_confidence": settings.ocr_fallback_min_confidence,
        "page_fraction": settings.ocr_fallback_page_fraction,
        "unconditional_types": sorted(OCR_UNCONDITIONAL_TYPES),
    }
    # Added only off the default, so a document-unit install keeps the
    # identity it has today and nothing reindexes. Switching to "page"
    # changes which engine reads which page, so its sources must reindex.
    if getattr(settings, "ocr_routing_unit", "document") != "document":
        payload["routing_unit"] = settings.ocr_routing_unit
        local_tier: dict[str, Any] = {"min_confidence": settings.ocr_local_min_confidence}
        # The resolved model identity (task 4.2): absent while unresolved,
        # present once the runtime resolves it. The page-unit digest moves
        # with this key, which is correct — the model changes what the
        # pages read as.
        if local_model_identity is not None:
            local_tier["model"] = local_model_identity
        payload["local_tier"] = local_tier
    return payload


def resolved_routing_payload(settings: Any) -> dict[str, Any]:
    """Build the routing payload with the resolved local model identity.

    Boundary wrapper for the composition path: resolves the local tier's
    model identity exactly once per process (the probe is cached), then
    delegates to :func:`ocr_routing_payload`. The probe runs only when its
    result can reach the payload — a non-``document`` routing unit with
    the OCR fallback enabled. Anywhere else the tier cannot run, so the
    model cannot change the emitted text and the payload stays put.

    The lazy import keeps pdf-inspector out of every import of this
    module; ``core`` reaching into ``integrations`` lazily inside a
    function follows the ``codebase_map`` → ``integrations.magika``
    precedent.

    Args:
        settings: Settings object carrying the routing gate, the routing
            unit and the local tier settings.

    Returns:
        The canonical routing payload, with ``local_tier.model`` when the
        probe resolved an identity under a ``page`` unit.
    """
    local_model_identity = None
    if getattr(settings, "ocr_routing_unit", "document") != "document" and getattr(
        settings, "ocr_fallback_enabled", False
    ):
        from ...integrations.pdf.page_routing import resolve_local_model_identity

        local_model_identity = resolve_local_model_identity(settings)
    return ocr_routing_payload(settings, local_model_identity=local_model_identity)


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
