"""Identity-driven re-ingestion tests for the OCR capability (task 2.14).

Spec: openspec/changes/improve-rag-input-quality-5/specs/async-ingestion/
spec.md — "New input-quality inputs SHALL participate in the complete index
identity". Every scenario below drives the REAL ``ingest_path_async`` plus
the ``source_state`` skip/replace path with stub-worker-backed fingerprints:
no Paddle, no network, no worker subprocess dispatch (the clean calibration
PDF stays on the ``pdf_inspector`` fast path, so the identity change is the
ONLY difference between ingestion legs).

The conservative inclusion rule (design D8) is exercised directly: the
fingerprint and routing gate are hashed for a file that never routes to
the worker, because unnecessary reprocessing is safer than stale chunks.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from omrg.capabilities import probe_ocr_worker, reset_ocr_fingerprint_cache
from omrg.core.ingestion.ocr_identity import (
    ocr_fingerprint_payload,
    ocr_routing_payload,
)
from omrg.core.ingestion.pipeline import ingest_path_async
from omrg.core.ingestion.source_state import SOURCE_INDEX_IDENTITY_KEY
from omrg.core.vectordb import get_default_store
from omrg.integrations.ocr_worker.fingerprint import (
    UNAVAILABLE_OCR_WORKER_FINGERPRINT,
)
from omrg.integrations.ocr_worker.managed import ManagedOcrClient

pytest.importorskip("pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)")

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_WORKER = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_worker.py"
CAL_CLEAN = REPO_ROOT / "tests" / "fixtures" / "pdf_baseline" / "calibration" / "cal_clean_text.pdf"


def _stub_command(mode: str) -> list[str]:
    """Build the stub worker launch command."""
    return [sys.executable, str(STUB_WORKER), "--mode", mode]


@pytest.fixture(autouse=True)
def _fresh_fingerprint_cache() -> Iterator[None]:
    """Isolate probe memoisation between tests."""
    reset_ocr_fingerprint_cache()
    yield
    reset_ocr_fingerprint_cache()


def _echo_fingerprint() -> Any:
    """The real available fingerprint probed from the stub worker."""
    fingerprint = probe_ocr_worker(_stub_command("echo"))
    assert fingerprint.available, "the echo stub capabilities probe must be healthy"
    return fingerprint


def _client(fingerprint: Any) -> ManagedOcrClient:
    """A managed client carrying the given resolved fingerprint.

    Construction starts nothing; the clean calibration PDF never dispatches
    a parse request, so the chosen fingerprint reaches the index identity
    without any subprocess work.
    """
    return ManagedOcrClient(
        fingerprint=fingerprint,
        command=_stub_command("echo"),
    )


async def _ingest(source: Path, settings: Any, client: ManagedOcrClient, collection: str) -> dict:
    """Run one ingestion leg with an injected client on a fresh collection."""
    return await ingest_path_async(
        str(source),
        effective_settings=settings,
        ocr_client=client,
        collection_name=collection,
    )


def _ocr_settings(effective_settings, **extra) -> Any:
    """Effective settings with the routing seam active and extraction off."""
    return effective_settings(
        pdf_reader="pdf_inspector",
        ocr_fallback_enabled=True,
        **{"metadata.extraction_mode": "disabled"},
        **extra,
    )


def _stored_identities(collection: str) -> set[str]:
    """Read the real stored ``source_index_identity`` values for a collection."""
    store = get_default_store()
    identities = {
        meta[SOURCE_INDEX_IDENTITY_KEY] for meta in store.iter_metadatas(collection) if meta
    }
    assert identities, f"no stored rows carry {SOURCE_INDEX_IDENTITY_KEY!r} in {collection}"
    return identities


# ── Canonical payload helpers ──────────────────────────────────────────────


def test_unavailable_fingerprint_payload_has_one_stable_shape() -> None:
    """The None default and the real constant produce the same payload.

    Pins the no-drift contract between ``ocr_identity``'s built-in
    unavailable shape and ``asdict(UNAVAILABLE_OCR_WORKER_FINGERPRINT)``
    (task 2.13: one stable unavailable fingerprint, never an omitted
    field, never a second shape).
    """
    assert ocr_fingerprint_payload(None) == asdict(UNAVAILABLE_OCR_WORKER_FINGERPRINT)
    assert ocr_fingerprint_payload(UNAVAILABLE_OCR_WORKER_FINGERPRINT) == asdict(
        UNAVAILABLE_OCR_WORKER_FINGERPRINT
    )


def test_routing_payload_echoes_the_three_gate_values(effective_settings) -> None:
    """The routing payload carries the gate values and the unconditional types."""
    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_fallback_min_confidence=0.5,
        ocr_fallback_page_fraction=0.25,
    )
    assert ocr_routing_payload(settings) == {
        "enabled": True,
        "min_confidence": 0.5,
        "page_fraction": 0.25,
        "unconditional_types": ["image_based", "scanned"],
    }


# ── Scenario: degraded extraction recovers when OCR becomes available ─────


async def test_unavailable_to_available_fingerprint_forces_reingestion(
    tmp_path: Path, effective_settings
) -> None:
    """A byte-identical source indexed while UNAVAILABLE is re-ingested.

    Spec scenario "Degraded extraction recovers when the OCR capability
    becomes available": the resolved OCR capability SHALL differ from the
    stored index identity, and the source SHALL NOT be reported as
    ``skipped_unchanged``.
    """
    source = tmp_path / "clean.pdf"
    source.write_bytes(CAL_CLEAN.read_bytes())
    settings = _ocr_settings(effective_settings)

    unavailable = _client(UNAVAILABLE_OCR_WORKER_FINGERPRINT)
    try:
        first = await _ingest(source, settings, unavailable, "ocr_id_unavail")
    finally:
        unavailable.close()
    assert first["file_details"][0]["status"] == "indexed"
    first_identities = _stored_identities("ocr_id_unavail")

    available = _client(_echo_fingerprint())
    try:
        second = await _ingest(source, settings, available, "ocr_id_unavail")
    finally:
        available.close()
    assert second["file_details"][0]["status"] != "skipped_unchanged", (
        "the capability transition must be an identity change (design D8)"
    )
    assert second["file_details"][0]["status"] == "indexed"
    second_identities = _stored_identities("ocr_id_unavail")
    assert len(first_identities) == len(second_identities) == 1, (
        "each leg must leave exactly one complete current version"
    )
    assert second_identities.isdisjoint(first_identities), (
        "the stored identity must change when the fingerprint changes"
    )


# ── Scenario: each fingerprint field independently forces reprocessing ────


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("protocol_version", "1.1"),
        ("packages", (("stub-worker", "1.1"),)),
        ("pipeline_identity", "other-pipeline"),
        ("pipeline_revision", "2"),
        ("model_identity", "other-model"),
        ("model_revision", "2"),
        ("output_schema_id", "other.ocr.parse_output"),
        ("output_schema_version", "2"),
    ],
)
async def test_each_fingerprint_field_change_prevents_skip(
    field: str, changed: Any, tmp_path: Path, effective_settings
) -> None:
    """Changing any one fingerprint field invalidates the stored identity."""
    source = tmp_path / "clean.pdf"
    source.write_bytes(CAL_CLEAN.read_bytes())
    settings = _ocr_settings(effective_settings)
    base = _echo_fingerprint()

    first_client = _client(base)
    try:
        first = await _ingest(source, settings, first_client, f"ocr_id_{field}")
    finally:
        first_client.close()
    assert first["file_details"][0]["status"] == "indexed"

    variant = replace(base, **{field: changed})
    second_client = _client(variant)
    try:
        second = await _ingest(source, settings, second_client, f"ocr_id_{field}")
    finally:
        second_client.close()
    assert second["file_details"][0]["status"] == "indexed", (
        f"changing fingerprint field {field!r} must prevent skipped_unchanged"
    )


# ── Scenario: unchanged input-quality inputs still skip ───────────────────


async def test_unchanged_fingerprint_preserves_skip(tmp_path: Path, effective_settings) -> None:
    """An unchanged canonical fingerprint keeps ``skipped_unchanged``.

    The second leg uses a FRESH client instance carrying an EQUAL
    fingerprint value, proving identity comparison is canonical (value)
    comparison, not object identity.
    """
    source = tmp_path / "clean.pdf"
    source.write_bytes(CAL_CLEAN.read_bytes())
    settings = _ocr_settings(effective_settings)
    base = _echo_fingerprint()

    first_client = _client(base)
    try:
        first = await _ingest(source, settings, first_client, "ocr_id_same")
    finally:
        first_client.close()
    assert first["file_details"][0]["status"] == "indexed"
    first_identities = _stored_identities("ocr_id_same")

    equal_client = _client(replace(base))
    try:
        second = await _ingest(source, settings, equal_client, "ocr_id_same")
    finally:
        equal_client.close()
    assert second["file_details"][0]["status"] == "skipped_unchanged"
    assert (
        first["file_details"][0]["source_version"] == second["file_details"][0]["source_version"]
    ), "equal content plus equal fingerprint must reproduce the source version"
    # The skip means nothing new landed: the stored identity set is
    # unchanged and still exactly one complete current version.
    assert _stored_identities("ocr_id_same") == first_identities
    assert len(first_identities) == 1


# ── Scenario: OCR routing configuration change forces reprocessing ────────


async def test_routing_configuration_change_alone_prevents_skip(
    tmp_path: Path, effective_settings
) -> None:
    """A routing-gate change alone invalidates the stored identity.

    Spec scenario "OCR routing configuration change forces reprocessing":
    only ``OCR_FALLBACK_MIN_CONFIDENCE`` changes (0.5 → 0.7) between legs
    — same fingerprint, same bytes, same chunking.
    """
    source = tmp_path / "clean.pdf"
    source.write_bytes(CAL_CLEAN.read_bytes())
    base = _echo_fingerprint()
    low = _ocr_settings(effective_settings, ocr_fallback_min_confidence=0.5)
    high = _ocr_settings(effective_settings, ocr_fallback_min_confidence=0.7)

    client = _client(base)
    try:
        first = await _ingest(source, low, client, "ocr_id_routing")
        first_identities = _stored_identities("ocr_id_routing")
        second = await _ingest(source, high, client, "ocr_id_routing")
    finally:
        client.close()
    assert first["file_details"][0]["status"] == "indexed"
    assert second["file_details"][0]["status"] == "indexed", (
        "a routing-configuration change alone must prevent skipped_unchanged"
    )
    second_identities = _stored_identities("ocr_id_routing")
    assert len(first_identities) == len(second_identities) == 1, (
        "each leg must leave exactly one complete current version"
    )
    assert second_identities.isdisjoint(first_identities), (
        "the stored identity must change when the routing gate changes"
    )


# ── Scenario: query instruction change alone does not force reprocessing ──


async def test_query_instruction_change_alone_still_skips(
    tmp_path: Path, effective_settings
) -> None:
    """Only ``EMBEDDING__QUERY_INSTRUCTION`` changes: identity is unchanged.

    Spec scenario "Query instruction change alone does not force
    reprocessing", asserted here against the schema-5 payload too: the
    instruction changes query vectors only and stays OUT of the document
    identity (design D8, proposal §6).
    """
    source = tmp_path / "clean.pdf"
    source.write_bytes(CAL_CLEAN.read_bytes())
    base = _echo_fingerprint()
    plain = _ocr_settings(effective_settings)
    instructed = _ocr_settings(
        effective_settings, **{"embedding.query_instruction": "retrieve evidence"}
    )

    client = _client(base)
    try:
        first = await _ingest(source, plain, client, "ocr_id_query")
        first_identities = _stored_identities("ocr_id_query")
        second = await _ingest(source, instructed, client, "ocr_id_query")
    finally:
        client.close()
    assert first["file_details"][0]["status"] == "indexed"
    assert second["file_details"][0]["status"] == "skipped_unchanged", (
        "the query instruction must stay out of the document index identity"
    )
    assert (
        first["file_details"][0]["source_version"] == second["file_details"][0]["source_version"]
    ), "equal content plus an instruction-only change must reproduce the version"
    assert _stored_identities("ocr_id_query") == first_identities
    assert len(first_identities) == 1


# ── Scenario: unconditional routing types participate in the index identity ─


def test_unconditional_types_are_in_the_routing_payload() -> None:
    """The routing payload carries the unconditional types for identity.

    The unconditional routing set decides which ``pdf_type`` values bypass
    the calibrated thresholds. Changing that set changes the routing
    decision for affected PDFs, so it MUST participate in the index
    identity to prevent stale ``skipped_unchanged`` results after a
    routing-rule fix.
    """
    payload = ocr_routing_payload(
        type(
            "S",
            (),
            {
                "ocr_fallback_enabled": True,
                "ocr_fallback_min_confidence": 0.5,
                "ocr_fallback_page_fraction": 0.5,
            },
        )()
    )
    assert "unconditional_types" in payload
    assert set(payload["unconditional_types"]) == {"scanned", "image_based"}
    assert "mixed" not in payload["unconditional_types"]


def test_routing_payload_unconditional_types_are_sorted() -> None:
    """The unconditional types are sorted for deterministic identity hashing."""
    payload = ocr_routing_payload(
        type(
            "S",
            (),
            {
                "ocr_fallback_enabled": False,
                "ocr_fallback_min_confidence": 0.0,
                "ocr_fallback_page_fraction": 0.0,
            },
        )()
    )
    assert payload["unconditional_types"] == sorted(payload["unconditional_types"])


def test_mixed_is_not_in_unconditional_types() -> None:
    """``mixed`` is deliberately excluded from the unconditional routing set.

    ``scanned`` and ``image_based`` both mean "the whole document is
    pictures", so no threshold can change the answer. ``mixed`` means
    "some pages carry text and some do not" — which is precisely the
    question ``ocr_fallback_page_fraction`` exists to answer, so routing
    it unconditionally skips the one check designed for it.
    """
    from omrg.core.ingestion.ocr_identity import OCR_UNCONDITIONAL_TYPES

    assert "mixed" not in OCR_UNCONDITIONAL_TYPES
    assert "scanned" in OCR_UNCONDITIONAL_TYPES
    assert "image_based" in OCR_UNCONDITIONAL_TYPES


def test_ocr_routing_constant_is_consistent_across_modules() -> None:
    """The routing module re-exports the identity module's constant (single source of truth)."""
    from omrg.core.ingestion.ocr_identity import OCR_UNCONDITIONAL_TYPES as identity_types
    from omrg.integrations.pdf.ocr_routing import OCR_UNCONDITIONAL_TYPES as routing_types

    assert identity_types is routing_types
