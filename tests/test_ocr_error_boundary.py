"""Post-dispatch failure and error-boundary tests through the real pipeline.

Task 2.9/2.9a: after a complete parse request is written and flushed, a
timeout, crash, unexpected output closure, malformed or mismatched
protocol response, or structured worker error MUST become a structured
per-file ingestion error. The failed source is never marked current,
the prior current version survives through the failure-safe
replacement path, later files continue, the worker is invalidated, and
nothing replays the failed request automatically.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from omrg.capabilities import probe_ocr_worker, reset_ocr_fingerprint_cache
from omrg.core.ingestion.pipeline import ingest_path_async
from omrg.core.vectordb import get_default_store
from omrg.integrations.ocr_worker.managed import ManagedOcrClient

pytest.importorskip("pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)")

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_WORKER = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_worker.py"
CAL_SCANNED = REPO_ROOT / "tests" / "fixtures" / "pdf_baseline" / "calibration" / "cal_scanned.pdf"


def _stub_command(mode: str) -> list[str]:
    """Build the stub worker launch command."""
    return [sys.executable, str(STUB_WORKER), "--mode", mode]


def _client(mode: str, *, request_timeout: float = 30.0) -> ManagedOcrClient:
    """A managed client whose capabilities probe is healthy (any mode)."""
    reset_ocr_fingerprint_cache()
    fingerprint = probe_ocr_worker(_stub_command("echo"))
    assert fingerprint.available
    return ManagedOcrClient(
        fingerprint=fingerprint,
        command=_stub_command(mode),
        request_timeout=request_timeout,
    )


@pytest.fixture(autouse=True)
def _fresh_fingerprint_cache() -> Iterator[None]:
    """Isolate probe memoisation between tests."""
    reset_ocr_fingerprint_cache()
    yield
    reset_ocr_fingerprint_cache()


@pytest.fixture
def batch_dir(tmp_path: Path) -> Path:
    """One OCR-required PDF twice (two sources) plus one plain text file."""
    good_txt = tmp_path / "good.txt"
    good_txt.write_text("plain companion file for batch continuation", encoding="utf-8")
    scanned_1 = tmp_path / "scanned_one.pdf"
    scanned_1.write_bytes(CAL_SCANNED.read_bytes())
    scanned_2 = tmp_path / "scanned_two.pdf"
    scanned_2.write_bytes(CAL_SCANNED.read_bytes())
    return tmp_path


def _ocr_settings(effective_settings, **extra):
    """Effective settings with the routing seam active and extraction off."""
    return effective_settings(
        pdf_reader="pdf_inspector",
        ocr_fallback_enabled=True,
        collection_name="ocr_boundary",
        **{"metadata.extraction_mode": "disabled"},
        **extra,
    )


async def _ingest(path: Path, settings, client: ManagedOcrClient | None, **extra):
    """Run one ingestion with an injected client on the shared test collection."""
    return await ingest_path_async(
        str(path),
        effective_settings=settings,
        ocr_client=client,
        collection_name="ocr_boundary",
        **extra,
    )


# ── Task 2.9a: every post-dispatch failure mode ───────────────────────────


@pytest.mark.parametrize(
    ("mode", "expected_code", "expected_generations"),
    [
        ("crash", "worker_crashed", 2),
        ("close-stdout", "worker_closed_output", 2),
        ("wrong-id", "protocol_violation", 2),
        ("bad-json", "protocol_violation", 2),
        # A structured worker error is a healthy exchange: the process
        # is retained and answers the second request (design D2.2).
        ("error", "stub_failure", 1),
    ],
)
async def test_post_dispatch_failures_are_structured_per_file_errors(
    mode: str, expected_code: str, expected_generations: int, batch_dir: Path, effective_settings
) -> None:
    """Each failure: correct structured error, batch continues, worker invalidated."""
    settings = _ocr_settings(effective_settings)
    client = _client(mode)
    try:
        result = await _ingest(batch_dir, settings, client)
        started_after_batch = client.is_started
    finally:
        client.close()

    by_name = {detail["file"]: detail for detail in result["file_details"]}
    for pdf_name in ("scanned_one.pdf", "scanned_two.pdf"):
        detail = by_name[pdf_name]
        assert detail["status"] == "failed", f"{mode}: partial markdown must not pass"
        assert expected_code in detail["error"], f"{mode}: {detail['error']}"
        # Reader exceptions are not IngestionStageError: the honest
        # existing boundary classification for them is "file".
        assert detail["failure_stage"] == "file"
    # The batch continued: the plain text file was indexed.
    assert by_name["good.txt"]["status"] == "indexed"
    # Fatal modes invalidate the worker (each attempt used a fresh
    # process, no replay on the dead handle); the structured-error mode
    # keeps the healthy process and reuses it for the second request.
    assert client.process_generations == expected_generations
    assert started_after_batch is (expected_generations == 1)


async def test_post_dispatch_timeout_is_a_structured_error(
    batch_dir: Path, effective_settings
) -> None:
    """A hanging worker fails the file at the configured request timeout."""
    settings = _ocr_settings(effective_settings, ocr_worker_request_timeout=1.0)
    client = _client("hang", request_timeout=1.0)
    try:
        result = await _ingest(batch_dir / "scanned_one.pdf", settings, client)
    finally:
        client.close()
    detail = result["file_details"][0]
    assert detail["status"] == "failed"
    assert "timeout" in detail["error"]
    assert client.is_started is False


# ── Prior current version preservation through the real mechanism ────────


async def test_failed_attempt_preserves_prior_current_version(
    batch_dir: Path, effective_settings
) -> None:
    """The failure-safe replacement path keeps the earlier successful version.

    Three phases against the same source file:

    1. indexed successfully through the echo worker (chunk_size 200);
    2. re-ingested under a DIFFERENT index identity (chunk_size 300)
       whose dispatch crashes — the file fails, nothing is written;
    3. re-ingested with the phase-1 identity — the store still holds
       the complete phase-1 current version, so the file reports
       ``skipped_unchanged`` rather than reprocessing.
    """
    settings = _ocr_settings(effective_settings)
    source = batch_dir / "scanned_one.pdf"

    ok_client = _client("echo")
    try:
        first = await _ingest(source, settings, ok_client, chunk_size=200)
    finally:
        ok_client.close()
    assert first["file_details"][0]["status"] == "indexed"

    crash_client = _client("crash")
    try:
        second = await _ingest(source, settings, crash_client, chunk_size=300)
    finally:
        crash_client.close()
    assert second["file_details"][0]["status"] == "failed"
    assert "worker_crashed" in second["file_details"][0]["error"]

    again_client = _client("echo")
    try:
        third = await _ingest(source, settings, again_client, chunk_size=200)
    finally:
        again_client.close()
    assert third["file_details"][0]["status"] == "skipped_unchanged", (
        "the prior current version must remain complete and matching"
    )


# ── Task 2.7 at pipeline level: pre-dispatch degradation ─────────────────


async def test_unavailable_worker_degrades_and_batch_continues(
    batch_dir: Path, effective_settings, caplog
) -> None:
    """OCR required but unavailable: honest degradation, batch continues.

    The scanned calibration fixture's partial markdown is EMPTY, so the
    degraded document legitimately produces no chunks: the file fails
    within the existing per-file boundary ("No chunks were produced"),
    nothing is fabricated, and the batch continues to the plain-text
    companion. The actionable diagnostic is logged. (The reader-level
    seam tests assert the kept-partial-markdown and diagnostics
    contract directly.)
    """
    settings = _ocr_settings(effective_settings)
    with caplog.at_level("WARNING"):
        result = await _ingest(batch_dir, settings, None)

    assert result["status"] == "ok", "degradation must not fail the whole batch"
    by_name = {detail["file"]: detail for detail in result["file_details"]}
    assert by_name["good.txt"]["status"] == "indexed"
    assert by_name["scanned_one.pdf"]["status"] == "failed"
    assert "No chunks were produced" in by_name["scanned_one.pdf"]["error"]
    assert "OCR_WORKER_COMMAND" in caplog.text
    assert "unavailable" in caplog.text


async def test_worker_path_stores_scalar_diagnostics(batch_dir: Path, effective_settings) -> None:
    """The worker path's stored metadata carries the four diagnostics."""
    settings = _ocr_settings(effective_settings)
    client = _client("echo")
    try:
        result = await _ingest(batch_dir / "scanned_one.pdf", settings, client)
    finally:
        client.close()
    assert result["file_details"][0]["status"] == "indexed"

    store = get_default_store()
    metadatas = [m for m in store.iter_metadatas("ocr_boundary") if m]
    scanned = [m for m in metadatas if m.get("file_name") == "scanned_one.pdf"]
    assert scanned
    for meta in scanned:
        assert meta["ocr_required"] is True
        assert meta["ocr_used"] is True
        assert meta["ocr_backend"] == "paddleocr_vl"
        assert isinstance(meta["pages_needing_ocr"], int)
        assert not isinstance(meta["pages_needing_ocr"], bool)
        assert not isinstance(meta["pages_needing_ocr"], list)


# ── Task 2.6a: engine ownership closes the worker ─────────────────────────


async def test_engine_close_releases_the_owned_worker(effective_settings) -> None:
    """Engine.ingest dispatches through its client; close() releases it."""
    from llama_index.core import Settings as LlamaIndexSettings

    from omrg.engine import Engine

    settings = _ocr_settings(effective_settings)
    client = _client("echo")
    engine = Engine(
        settings,
        store=get_default_store(),
        embed_model=LlamaIndexSettings.embed_model,
        ocr_client=client,
    )
    tmp_dir = CAL_SCANNED.parent
    try:
        result = await engine.ingest(str(CAL_SCANNED), collection_name="ocr_boundary")
        assert result["file_details"][0]["status"] == "indexed"
        assert client.is_started is True
    finally:
        engine.close()
    assert client.is_started is False
    with pytest.raises(RuntimeError, match="closed"):
        client.parse(str(CAL_SCANNED))
    _ = tmp_dir  # fixture dir only for symmetry; no writes
