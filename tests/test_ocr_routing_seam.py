"""Routing-seam tests through the reader contract (tasks 2.3–2.5, 2.7, 2.8, 2.10).

Reader-level coverage against the committed calibration fixtures and
the stub worker: clean text-based PDFs never start the worker,
complex text layouts stay on pdf-inspector, scanned fixtures dispatch
the whole PDF and reuse one process, an unavailable worker degrades
deterministically, and every branch stamps the four additive OCR
diagnostics with ``pages_needing_ocr`` as a scalar count.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from omrg.capabilities import probe_ocr_worker, reset_ocr_fingerprint_cache
from omrg.integrations.ocr_worker.managed import ManagedOcrClient
from omrg.integrations.pdf.factory import build_pdf_reader
from omrg.integrations.pdf.ocr_routing import (
    OCR_BACKEND_FAST_PATH,
    OCR_BACKEND_WORKER_PATH,
    OcrRoutedPdfInspector,
)
from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

pdf_inspector_lib = pytest.importorskip(
    "pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_WORKER = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_worker.py"
CALIBRATION = REPO_ROOT / "tests" / "fixtures" / "pdf_baseline" / "calibration"


def _stub_command(mode: str) -> list[str]:
    """Build the stub worker launch command."""
    return [sys.executable, str(STUB_WORKER), "--mode", mode]


@pytest.fixture(autouse=True)
def _fresh_fingerprint_cache() -> Iterator[None]:
    """Isolate probe memoisation between tests."""
    reset_ocr_fingerprint_cache()
    yield
    reset_ocr_fingerprint_cache()


def _echo_client() -> ManagedOcrClient:
    """A managed client around the healthy echo stub worker."""
    fingerprint = probe_ocr_worker(_stub_command("echo"))
    assert fingerprint.available
    return ManagedOcrClient(fingerprint=fingerprint, command=_stub_command("echo"))


def _routed_reader(client: ManagedOcrClient | None, effective_settings) -> OcrRoutedPdfInspector:
    """Build the seam exactly as the factory composes it (fallback on)."""
    reader = build_pdf_reader(
        "pdf_inspector",
        effective_settings(pdf_reader="pdf_inspector", ocr_fallback_enabled=True),
        ocr_client=client,
    )
    assert isinstance(reader, OcrRoutedPdfInspector)
    return reader


# ── Task 2.8: laziness — clean PDFs never start the worker ────────────────


def test_clean_text_pdf_never_starts_the_worker(effective_settings) -> None:
    """A clean text-based PDF neither spawns the process nor loads its model."""
    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        docs = reader.load_data(file=CALIBRATION / "cal_clean_text.pdf")
        meta = docs[0].metadata
        assert meta["ocr_required"] is False
        assert meta["ocr_used"] is False
        assert meta["ocr_backend"] == OCR_BACKEND_FAST_PATH
        assert meta["pages_needing_ocr"] == 0
        assert client.is_started is False
        assert client.process_generations == 0
    finally:
        client.close()


def test_complex_text_layout_stays_on_pdf_inspector(effective_settings) -> None:
    """The table-heavy calibration fixture never reaches the worker (task 2.5).

    cal_table_text.pdf is the committed complex-layout calibration
    fixture: text_based at confidence 1.0 with no flagged pages.
    Layout complexity alone must not select OCR.
    """
    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        docs = reader.load_data(file=CALIBRATION / "cal_table_text.pdf")
        meta = docs[0].metadata
        assert meta["pdf_type"] == "text_based"
        assert meta["ocr_required"] is False
        assert meta["ocr_used"] is False
        assert meta["ocr_backend"] == OCR_BACKEND_FAST_PATH
        assert client.process_generations == 0
    finally:
        client.close()


def test_fallback_disabled_returns_the_plain_reader(effective_settings) -> None:
    """Without OCR_FALLBACK_ENABLED the factory composes no seam at all."""
    reader = build_pdf_reader("pdf_inspector", effective_settings(pdf_reader="pdf_inspector"))
    assert type(reader) is PdfInspectorReader


# ── Tasks 2.3/2.4: scanned fixtures dispatch the whole PDF ────────────────


def test_scanned_fixture_dispatches_and_replaces_extraction(effective_settings) -> None:
    """The worker result replaces the partial pdf-inspector extraction."""
    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        docs = reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
        assert len(docs) == 1
        text = docs[0].get_content()
        meta = docs[0].metadata
        assert text.startswith("# Stub extraction"), "worker Markdown replaced the empty partial"
        assert str(CALIBRATION / "cal_scanned.pdf") in text, "whole PDF was routed"
        assert meta["ocr_required"] is True
        assert meta["ocr_used"] is True
        assert meta["ocr_backend"] == OCR_BACKEND_WORKER_PATH
        assert meta["ocr_used"] is True and meta["ocr_required"] is True
        # Honest provenance: the inspection evidence stays authoritative.
        assert meta["pdf_type"] == "scanned"
        assert meta["pdf_confidence"] == pytest.approx(0.9)
        assert meta["page_count"] == 1
        assert client.is_started is True
        assert client.process_generations == 1
    finally:
        client.close()


def test_second_ocr_request_reuses_the_same_process(effective_settings) -> None:
    """Two scanned files, one subprocess (single spawn assertion)."""
    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
        underlying = client._client
        assert underlying is not None and underlying._process is not None
        first_pid = underlying._process.pid
        docs = reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
        assert docs[0].metadata["ocr_used"] is True
        assert client.process_generations == 1
        reused = client._client
        assert reused is not None and reused._process is not None
        assert reused._process.pid == first_pid
    finally:
        client.close()


# ── Task 2.7: unavailable worker degrades deterministically ───────────────


def test_unavailable_client_keeps_partial_markdown_and_degrades(effective_settings, caplog) -> None:
    """ocr_required=True, ocr_used=False: honest degradation, no fabrication."""
    reader = _routed_reader(None, effective_settings)  # no client wired
    with caplog.at_level("WARNING"):
        docs = reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
    meta = docs[0].metadata
    assert meta["ocr_required"] is True
    assert meta["ocr_used"] is False
    assert meta["ocr_backend"] == OCR_BACKEND_FAST_PATH
    assert meta["pages_needing_ocr"] == 1
    # The partial (empty) pdf-inspector markdown is kept as-is.
    assert docs[0].get_content() == ""
    assert "OCR_WORKER_COMMAND" in caplog.text
    assert "unavailable" in caplog.text


def test_unavailable_fingerprint_client_degrades_the_same_way(effective_settings) -> None:
    """A probed-unavailable fingerprint degrades identically to no client."""
    from omrg.capabilities import UNAVAILABLE_OCR_WORKER_FINGERPRINT

    client = ManagedOcrClient(
        fingerprint=UNAVAILABLE_OCR_WORKER_FINGERPRINT, command=_stub_command("echo")
    )
    try:
        reader = _routed_reader(client, effective_settings)
        docs = reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
        assert docs[0].metadata["ocr_required"] is True
        assert docs[0].metadata["ocr_used"] is False
        assert client.process_generations == 0  # never spawned
    finally:
        client.close()


def test_degraded_result_still_indexes_as_a_document(effective_settings) -> None:
    """The degraded path returns a usable Document, never an exception."""
    reader = _routed_reader(None, effective_settings)
    docs = reader.load_data(file=CALIBRATION / "cal_scanned.pdf")
    assert len(docs) == 1
    assert docs[0].metadata["file_name"] == "cal_scanned.pdf"


# ── Task 2.10: diagnostics shape on every branch ──────────────────────────


@pytest.mark.parametrize("fixture", ["cal_clean_text.pdf", "cal_table_text.pdf", "cal_scanned.pdf"])
def test_pages_needing_ocr_is_a_scalar_on_every_branch(fixture: str, effective_settings) -> None:
    """Stored metadata carries a scalar int count, never the page list."""
    client = _echo_client()
    try:
        reader = _routed_reader(client, effective_settings)
        docs = reader.load_data(file=CALIBRATION / fixture)
        value = docs[0].metadata["pages_needing_ocr"]
        assert isinstance(value, int) and not isinstance(value, bool)
        assert value in (0, 1)
    finally:
        client.close()


# ── Mixed-PDF dispatch boundary: OCR enabled, thresholds at 0.0 ──────────


def _mock_inner_document(pdf_type: str, confidence: float, pages_needing_ocr: int, page_count: int):
    """Build a mock inner reader returning one document with inspection evidence."""
    from llama_index.core import Document

    return lambda file, *args, **kwargs: [
        Document(
            text="partial extraction",
            metadata={
                "pdf_type": pdf_type,
                "pdf_confidence": confidence,
                "pages_needing_ocr": pages_needing_ocr,
                "page_count": page_count,
                "file_name": str(file),
            },
        )
    ]


def test_mixed_pdf_with_ocr_enabled_zero_thresholds_stays_on_fast_path(
    effective_settings, monkeypatch
) -> None:
    """A mixed PDF with OCR enabled and both thresholds at 0.0 stays on pdf-inspector.

    The reader dispatch boundary follows the gate: 0.0 sentinels are
    disabled, so a mixed classification does not route to the worker even
    when OCR fallback is enabled. The worker is never started.
    """
    client = _echo_client()
    try:
        settings = effective_settings(
            pdf_reader="pdf_inspector",
            ocr_fallback_enabled=True,
            ocr_fallback_min_confidence=0.0,
            ocr_fallback_page_fraction=0.0,
        )
        reader = build_pdf_reader("pdf_inspector", settings, ocr_client=client)
        assert isinstance(reader, OcrRoutedPdfInspector)
        # Mock the inner reader to return a mixed-classification document.
        reader._inner.load_data = _mock_inner_document(
            pdf_type="mixed",
            confidence=0.76,
            pages_needing_ocr=10,
            page_count=991,
        )
        docs = reader.load_data(file=Path("/fake/mixed.pdf"))
        meta = docs[0].metadata
        assert meta["ocr_required"] is False
        assert meta["ocr_used"] is False
        assert meta["ocr_backend"] == OCR_BACKEND_FAST_PATH
        assert client.is_started is False
        assert client.process_generations == 0
    finally:
        client.close()


def test_scanned_pdf_with_ocr_enabled_zero_thresholds_dispatches_worker(
    effective_settings, monkeypatch
) -> None:
    """A scanned PDF with OCR enabled and both thresholds at 0.0 dispatches the worker.

    Scanned is unconditional, so it routes regardless of threshold values.
    The worker is started and the extraction is replaced.
    """
    client = _echo_client()
    try:
        settings = effective_settings(
            pdf_reader="pdf_inspector",
            ocr_fallback_enabled=True,
            ocr_fallback_min_confidence=0.0,
            ocr_fallback_page_fraction=0.0,
        )
        reader = build_pdf_reader("pdf_inspector", settings, ocr_client=client)
        assert isinstance(reader, OcrRoutedPdfInspector)
        reader._inner.load_data = _mock_inner_document(
            pdf_type="scanned",
            confidence=0.9,
            pages_needing_ocr=1,
            page_count=1,
        )
        docs = reader.load_data(file=Path("/fake/scanned.pdf"))
        meta = docs[0].metadata
        assert meta["ocr_required"] is True
        assert meta["ocr_used"] is True
        assert meta["ocr_backend"] == OCR_BACKEND_WORKER_PATH
        assert client.is_started is True
        assert client.process_generations == 1
    finally:
        client.close()


def test_image_based_pdf_with_ocr_enabled_zero_thresholds_dispatches_worker(
    effective_settings, monkeypatch
) -> None:
    """An image-based PDF with OCR enabled and both thresholds at 0.0 dispatches the worker.

    Image-based is unconditional, so it routes regardless of threshold values.
    """
    client = _echo_client()
    try:
        settings = effective_settings(
            pdf_reader="pdf_inspector",
            ocr_fallback_enabled=True,
            ocr_fallback_min_confidence=0.0,
            ocr_fallback_page_fraction=0.0,
        )
        reader = build_pdf_reader("pdf_inspector", settings, ocr_client=client)
        assert isinstance(reader, OcrRoutedPdfInspector)
        reader._inner.load_data = _mock_inner_document(
            pdf_type="image_based",
            confidence=0.95,
            pages_needing_ocr=1,
            page_count=1,
        )
        docs = reader.load_data(file=Path("/fake/image.pdf"))
        meta = docs[0].metadata
        assert meta["ocr_required"] is True
        assert meta["ocr_used"] is True
        assert meta["ocr_backend"] == OCR_BACKEND_WORKER_PATH
        assert client.is_started is True
    finally:
        client.close()


def test_mixed_pdf_with_ocr_enabled_zero_thresholds_preserves_diagnostics(
    effective_settings, monkeypatch
) -> None:
    """The mixed fast path still stamps the four additive OCR diagnostics."""
    client = _echo_client()
    try:
        settings = effective_settings(
            pdf_reader="pdf_inspector",
            ocr_fallback_enabled=True,
            ocr_fallback_min_confidence=0.0,
            ocr_fallback_page_fraction=0.0,
        )
        reader = build_pdf_reader("pdf_inspector", settings, ocr_client=client)
        assert isinstance(reader, OcrRoutedPdfInspector)
        reader._inner.load_data = _mock_inner_document(
            pdf_type="mixed",
            confidence=0.5,
            pages_needing_ocr=3,
            page_count=10,
        )
        docs = reader.load_data(file=Path("/fake/mixed.pdf"))
        meta = docs[0].metadata
        assert "ocr_required" in meta
        assert "ocr_used" in meta
        assert "ocr_backend" in meta
        assert "pages_needing_ocr" in meta
        assert meta["pages_needing_ocr"] == 3
        assert isinstance(meta["pages_needing_ocr"], int)
    finally:
        client.close()
