"""Identity for the two OCR routes and maths routing (task 6.1).

Change modular-ocr-workers-dots-mocr, design D7. Scenarios from
``specs/pdf-reader/spec.md`` ("Source index identity SHALL include the
resolved OCR worker fingerprint", now per route) and
``specs/maths-page-routing/spec.md`` ("Maths routing SHALL participate in
the source index identity").

The real ``ingest_path_async`` runs on the clean calibration PDF, which
stays on the pdf-inspector fast path and uses no maths font, so the
identity is the only difference between legs.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from omrg.capabilities import probe_ocr_worker, reset_ocr_fingerprint_cache
from omrg.core.ingestion import source_state
from omrg.core.ingestion.ocr_identity import maths_routing_payload, route_fingerprints
from omrg.core.ingestion.pipeline import ingest_path_async
from omrg.integrations.ocr_worker.fingerprint import UNAVAILABLE_OCR_WORKER_FINGERPRINT
from omrg.integrations.ocr_worker.managed import ManagedOcrClient
from omrg.integrations.ocr_worker.routes import OcrRoutes
from omrg.integrations.pdf import maths_pages

pytest.importorskip("pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)")

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_WORKER = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_worker.py"
CAL_CLEAN = REPO_ROOT / "tests" / "fixtures" / "pdf_baseline" / "calibration" / "cal_clean_text.pdf"


@pytest.fixture(autouse=True)
def _fresh_fingerprint_cache() -> Iterator[None]:
    reset_ocr_fingerprint_cache()
    yield
    reset_ocr_fingerprint_cache()


def _fingerprint(backend_id: str) -> Any:
    command = [sys.executable, str(STUB_WORKER), "--backend-id", backend_id]
    fingerprint = probe_ocr_worker(command)
    assert fingerprint.available
    return fingerprint


def _routes(primary: Any, fallback: Any) -> OcrRoutes:
    """Routes whose clients carry the given fingerprints; nothing dispatches."""
    command = [sys.executable, str(STUB_WORKER)]
    return OcrRoutes(
        primary=ManagedOcrClient(fingerprint=primary, command=command),
        fallback=ManagedOcrClient(fingerprint=fallback, command=command),
    )


def _settings(effective_settings: Any, **extra: Any) -> Any:
    return effective_settings(
        pdf_reader="pdf_inspector",
        ocr_fallback_enabled=True,
        **{"metadata.extraction_mode": "disabled"},
        **extra,
    )


async def _status(source: Path, settings: Any, routes: OcrRoutes, collection: str) -> str:
    try:
        result = await ingest_path_async(
            str(source), effective_settings=settings, ocr_client=routes, collection_name=collection
        )
    finally:
        routes.close()
    return result["file_details"][0]["status"]


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "clean.pdf"
    path.write_bytes(CAL_CLEAN.read_bytes())
    return path


# ── Fallback-route fingerprint (pdf-reader delta) ──────────────────────────


async def test_provisioning_the_fallback_triggers_reingestion(
    source: Path, effective_settings: Any
) -> None:
    """A fallback going from unavailable to available changes the identity."""
    settings = _settings(effective_settings)
    primary = _fingerprint("dots_mocr")
    first = await _status(
        source, settings, _routes(primary, UNAVAILABLE_OCR_WORKER_FINGERPRINT), "fb_prov"
    )
    second = await _status(
        source, settings, _routes(primary, _fingerprint("paddleocr_vl")), "fb_prov"
    )
    assert first == "indexed"
    assert second == "indexed", "the fallback's fingerprint must reach the identity"


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("packages", (("paddleocr", "9.9"),)),
        ("model_revision", "2"),
        ("backend_id", "other_engine"),
    ],
)
async def test_fallback_contract_change_triggers_reingestion(
    source: Path, effective_settings: Any, field: str, changed: Any
) -> None:
    """A package, model or engine change on the fallback route re-ingests."""
    settings = _settings(effective_settings)
    primary, fallback = _fingerprint("dots_mocr"), _fingerprint("paddleocr_vl")
    assert await _status(source, settings, _routes(primary, fallback), f"fb_{field}") == "indexed"
    variant = replace(fallback, **{field: changed})
    assert await _status(source, settings, _routes(primary, variant), f"fb_{field}") == "indexed"


async def test_unchanged_routes_and_maths_inputs_still_skip(
    source: Path, effective_settings: Any
) -> None:
    """Spec: unchanged fingerprints and maths inputs keep ``skipped_unchanged``."""
    settings = _settings(effective_settings)
    primary, fallback = _fingerprint("dots_mocr"), _fingerprint("paddleocr_vl")
    assert await _status(source, settings, _routes(primary, fallback), "same") == "indexed"
    again = _routes(replace(primary), replace(fallback))
    assert await _status(source, settings, again, "same") == "skipped_unchanged"


# ── Maths routing block (maths-page-routing) ───────────────────────────────


async def test_toggling_maths_routing_triggers_reingestion(
    source: Path, effective_settings: Any
) -> None:
    """Spec: "Toggling maths routing triggers re-ingestion"."""
    primary, fallback = _fingerprint("dots_mocr"), _fingerprint("paddleocr_vl")
    on = _settings(effective_settings)
    off = _settings(effective_settings, ocr_maths_routing_enabled=False)
    assert await _status(source, on, _routes(primary, fallback), "maths_toggle") == "indexed"
    assert await _status(source, off, _routes(primary, fallback), "maths_toggle") == "indexed"


async def test_detector_change_triggers_reingestion(
    source: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec: "A detector change triggers re-ingestion"."""
    settings = _settings(effective_settings)
    primary, fallback = _fingerprint("dots_mocr"), _fingerprint("paddleocr_vl")
    assert await _status(source, settings, _routes(primary, fallback), "maths_det") == "indexed"
    monkeypatch.setattr(maths_pages, "MATHS_DETECTOR_VERSION", 2)
    assert await _status(source, settings, _routes(primary, fallback), "maths_det") == "indexed"


def test_fraction_change_moves_the_identity(effective_settings: Any) -> None:
    """The maths page fraction is part of the identity."""
    a = _identity(_settings(effective_settings))
    b = _identity(_settings(effective_settings, ocr_maths_page_fraction=0.2))
    assert a != b


def test_maths_block_reads_injected_settings(effective_settings: Any) -> None:
    """The block echoes the resolved flag, fraction and detector version."""
    settings = _settings(effective_settings, ocr_maths_page_fraction=0.3)
    assert maths_routing_payload(settings) == {
        "enabled": True,
        "page_fraction": 0.3,
        "detector_version": maths_pages.MATHS_DETECTOR_VERSION,
    }


# ── The shared schema bump (design D7) ─────────────────────────────────────


def _identity(settings: Any, **kwargs: Any) -> str:
    return source_state.build_index_identity(
        settings, content_type="application/pdf", chunk_size=512, chunk_overlap=100, **kwargs
    )


def test_a_schema_6_source_indexed_before_this_change_reprocesses(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The schema stays 6 (shared bump), yet a pre-change schema-6 digest moves.

    The pre-change payload is today's payload without the fallback
    fingerprint, the maths block, and the fingerprint's ``backend_id``.
    Its digest differs from today's, so every source indexed under the
    earlier schema-6 payload reprocesses once. The digest covers the
    whole payload, never the schema number alone.
    """
    settings = _settings(effective_settings)
    payloads: list[dict] = []

    class _Recorder:
        def dumps(self, payload: Any, **kwargs: Any) -> str:
            payloads.append(payload)
            return json.dumps(payload, **kwargs)

    monkeypatch.setattr(source_state, "json", _Recorder())
    today = _identity(settings, ocr_worker_fingerprint=_fingerprint("dots_mocr"))
    payload = payloads[-1]
    assert payload["schema"] == 6
    before = dict(payload)
    del before["ocr_fallback_fingerprint"], before["maths_routing"]
    before["ocr_worker_fingerprint"] = {
        k: v for k, v in payload["ocr_worker_fingerprint"].items() if k != "backend_id"
    }
    before["embedding_text"] = {
        "excluded_keys": [
            k for k in payload["embedding_text"]["excluded_keys"] if k != "pages_maths_font"
        ]
    }
    monkeypatch.setattr(source_state, "json", json)
    canonical = json.dumps(before, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    import hashlib

    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() != today


def test_route_fingerprints_of_routes_client_and_none() -> None:
    """Routes give both fingerprints; one client is primary-only; None is none."""
    fp = UNAVAILABLE_OCR_WORKER_FINGERPRINT
    routes = OcrRoutes(primary=type("C", (), {"fingerprint": fp})())
    assert route_fingerprints(routes) == (fp, fp)
    single = type("C", (), {"fingerprint": fp})()
    assert route_fingerprints(single) == (fp, None)
    assert route_fingerprints(None) == (None, None)
