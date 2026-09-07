"""Owner-scoped lifecycle tests for the managed OCR worker client (task 2.6a).

The managed wrapper owns the subprocess lifecycle around the wave-1
client: construction starts nothing, the first parse lazily starts one
process, healthy processes are reused, a closed owner rejects further
requests, and a failed request invalidates the process so the NEXT
request lazily starts a fresh one without replaying the failed one
(design D2.2).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from omrg.capabilities import (
    UNAVAILABLE_OCR_WORKER_FINGERPRINT,
    probe_ocr_worker,
    reset_ocr_fingerprint_cache,
)
from omrg.integrations.ocr_worker import OcrWorkerError
from omrg.integrations.ocr_worker.fingerprint import OcrWorkerFingerprint
from omrg.integrations.ocr_worker.managed import ManagedOcrClient

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_WORKER = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_worker.py"


def _stub_command(mode: str) -> list[str]:
    """Build the stub worker launch command for one mode."""
    return [sys.executable, str(STUB_WORKER), "--mode", mode]


@pytest.fixture(autouse=True)
def _fresh_fingerprint_cache() -> None:
    """Keep probe memoisation out of these lifecycle tests' way."""
    reset_ocr_fingerprint_cache()


@pytest.fixture
def available_fingerprint() -> OcrWorkerFingerprint:
    """A probed, available fingerprint for the healthy stub worker."""
    fingerprint = probe_ocr_worker(_stub_command("echo"))
    assert fingerprint.available
    return fingerprint


@pytest.fixture
def small_pdf(tmp_path: Path) -> Path:
    """A minimal valid-enough PDF file for request payloads."""
    pdf = tmp_path / "small.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF\n")
    return pdf


# ── Laziness and reuse ─────────────────────────────────────────────────────


def test_construction_starts_nothing(available_fingerprint: OcrWorkerFingerprint) -> None:
    """A cheap client holds no process until the first dispatch (D2.2)."""
    client = ManagedOcrClient(fingerprint=available_fingerprint, command=_stub_command("echo"))
    assert client.is_started is False
    assert client.process_generations == 0


def test_first_parse_starts_one_process_and_later_parses_reuse_it(
    available_fingerprint: OcrWorkerFingerprint, small_pdf: Path
) -> None:
    """One spawn for the first dispatch; subsequent requests reuse it."""
    client = ManagedOcrClient(fingerprint=available_fingerprint, command=_stub_command("echo"))
    try:
        for _ in range(3):
            result = client.parse(str(small_pdf))
            assert result.metadata["ocr_backend"] == "stub-worker"
        assert client.is_started is True
        assert client.process_generations == 1
    finally:
        client.close()


# ── Owner-scoped close ─────────────────────────────────────────────────────


def test_close_stops_the_worker_and_rejects_further_requests(
    available_fingerprint: OcrWorkerFingerprint, small_pdf: Path
) -> None:
    """Engine-style close: bounded shutdown, then no further dispatch."""
    client = ManagedOcrClient(fingerprint=available_fingerprint, command=_stub_command("echo"))
    client.parse(str(small_pdf))
    assert client.is_started is True
    client.close()
    assert client.is_started is False
    with pytest.raises(RuntimeError, match="closed"):
        client.parse(str(small_pdf))
    client.close()  # idempotent


# ── Unavailable fingerprint: pre-dispatch guard ────────────────────────────


def test_unavailable_fingerprint_never_spawns(small_pdf: Path) -> None:
    """A pre-dispatch unavailability is a structured error, not a spawn."""
    client = ManagedOcrClient(
        fingerprint=UNAVAILABLE_OCR_WORKER_FINGERPRINT,
        command=_stub_command("echo"),
    )
    with pytest.raises(OcrWorkerError) as excinfo:
        client.parse(str(small_pdf))
    assert excinfo.value.code == "worker_unavailable"
    assert client.process_generations == 0
    assert client.is_started is False


def test_empty_command_client_is_unavailable_by_fingerprint() -> None:
    """An empty command yields the stable unavailable fingerprint (2.6b)."""
    client = ManagedOcrClient(fingerprint=UNAVAILABLE_OCR_WORKER_FINGERPRINT, command=[])
    assert client.fingerprint is UNAVAILABLE_OCR_WORKER_FINGERPRINT
    assert client.is_available is False


# ── Failure invalidation and lazy restart ─────────────────────────────────


def test_failed_process_is_discarded_and_next_request_starts_fresh(
    small_pdf: Path,
) -> None:
    """After a crash the handle is discarded; a later request respawns (D2.2).

    The failed request is not replayed: the first parse raises exactly
    once, and the second parse is a NEW request that gets a NEW
    process (generation 2).
    """
    fingerprint = probe_ocr_worker(_stub_command("crash"))
    assert fingerprint.available  # the capabilities command is healthy
    client = ManagedOcrClient(fingerprint=fingerprint, command=_stub_command("crash"))
    try:
        with pytest.raises(OcrWorkerError) as first:
            client.parse(str(small_pdf))
        assert first.value.code == "worker_crashed"
        assert client.is_started is False  # invalidated immediately
        with pytest.raises(OcrWorkerError) as second:
            client.parse(str(small_pdf))
        assert second.value.code == "worker_crashed"
        assert client.process_generations == 2  # a fresh process per attempt
    finally:
        client.close()


@pytest.mark.parametrize("mode", ["crash", "close-stdout", "bad-json", "wrong-id"])
def test_fatal_modes_invalidate_and_respawn(mode: str, small_pdf: Path) -> None:
    """Crash, output closure, and protocol failures all discard the process."""
    fingerprint = probe_ocr_worker(_stub_command(mode))
    client = ManagedOcrClient(fingerprint=fingerprint, command=_stub_command(mode))
    try:
        with pytest.raises(OcrWorkerError):
            client.parse(str(small_pdf))
        assert client.is_started is False
        with pytest.raises(OcrWorkerError):
            client.parse(str(small_pdf))
        assert client.process_generations == 2
    finally:
        client.close()


def test_structured_worker_error_keeps_the_process_healthy(small_pdf: Path) -> None:
    """A worker-reported error is a healthy exchange: no invalidation (D2.2)."""
    fingerprint = probe_ocr_worker(_stub_command("error"))
    client = ManagedOcrClient(fingerprint=fingerprint, command=_stub_command("error"))
    try:
        with pytest.raises(OcrWorkerError) as first:
            client.parse(str(small_pdf))
        assert first.value.code == "stub_failure"
        assert client.is_started is True  # process retained
        with pytest.raises(OcrWorkerError) as second:
            client.parse(str(small_pdf))
        assert second.value.code == "stub_failure"
        assert client.process_generations == 1  # same subprocess answered both
    finally:
        client.close()


def test_request_timeout_is_passed_through(
    available_fingerprint: OcrWorkerFingerprint, small_pdf: Path
) -> None:
    """The configured request timeout bounds every terminal-response wait."""
    fingerprint = probe_ocr_worker(_stub_command("hang"))
    client = ManagedOcrClient(
        fingerprint=fingerprint, command=_stub_command("hang"), request_timeout=1.0
    )
    try:
        with pytest.raises(OcrWorkerError) as excinfo:
            client.parse(str(small_pdf))
        assert excinfo.value.code == "timeout"
        assert client.is_started is False
    finally:
        client.close()
