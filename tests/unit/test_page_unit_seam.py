"""Page-unit routing through the reader seam (tasks 4.4, 4.5c, 4.6).

The ``page`` routing unit wired end to end: per-page evidence from a full
scan, the local OCR tier on every flagged page, one escalation request
carrying exactly the pages the local tier cannot read, and the merge back
into one document with the four page-source counts.

Everything external is stubbed in ``sys.modules``: the pdf-inspector scan
and its selective OCR never touch a real PDF, and the worker client is an
in-process fake. The inner reader is a fake document source, because the
seam under test is the routing around it, not the adapter inside.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from llama_index.core import Document

from omrg.integrations.ocr_worker.client import OcrWorkerError
from omrg.integrations.ocr_worker.protocol import make_success
from omrg.integrations.pdf.ocr_routing import OcrPostDispatchError, OcrRoutedPdfInspector
from omrg.integrations.pdf.page_routing import OCR_BACKEND_FAST_PATH, OCR_BACKEND_LOCAL_OCR

pytest.importorskip("pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)")


class _FakeInner:
    """Inner reader standing in for the pdf-inspector adapter."""

    def __init__(self, *, text: str = "", metadata: dict | None = None) -> None:
        self._document = Document(text=text, metadata=dict(metadata or {}))

    def load_data(self, file, *args, **kwargs) -> list:
        return [self._document]


class _FakeWorker:
    """In-process worker client recording every parse request."""

    def __init__(
        self,
        *,
        available: bool = True,
        protocol_version: str = "1.1",
        pages_markdown=None,
        error: Exception | None = None,
    ):
        self.fingerprint = SimpleNamespace(available=available, protocol_version=protocol_version)
        self.calls: list[dict] = []
        self._pages_markdown = pages_markdown
        self._error = error

    def parse(self, pdf_path: str, *, pages=None, timeout=None):
        self.calls.append({"path": pdf_path, "pages": list(pages) if pages is not None else None})
        if self._error is not None:
            raise self._error
        return make_success(
            "req",
            "\n\n".join(self._pages_markdown or []),
            ocr_backend="paddleocr-vl",
            page_count=len(pages or []),
            pages_markdown=self._pages_markdown,
        )


def _scan_page(index: int, markdown: str, needs_ocr: bool):
    """One extract_pages_markdown page, numbered from 0 as the library does."""
    return SimpleNamespace(page=index, markdown=markdown, needs_ocr=needs_ocr, ocr_reason=None)


def _ocr_page(page: int, markdown: str, confidence: float | None, hosted: bool = False):
    """One process_pdf_with_ocr page, numbered from 1 as the OCR API does."""
    provenance = SimpleNamespace(
        source="ocr",
        ocr_confidence=confidence,
        ocr_model=SimpleNamespace(name="pp-ocrv6-small", revision="oar-ocr-v0.7.0"),
        hosted_recommended=hosted,
        warnings=[],
    )
    return SimpleNamespace(page_number=page, markdown=markdown, provenance=provenance)


class _EngineCalls:
    """Recording stub for the pdf_inspector module's two entry points."""

    def __init__(self, scan_pages, ocr_pages_by_call=None, ocr_error: Exception | None = None):
        self.scan_calls: list[str] = []
        self.ocr_calls: list[dict] = []
        self._scan_pages = scan_pages
        self._ocr_pages_by_call = list(ocr_pages_by_call or [])
        self._ocr_error = ocr_error

    def extract_pages_markdown(self, path: str):
        self.scan_calls.append(path)
        return SimpleNamespace(pages=list(self._scan_pages))

    def process_pdf_with_ocr(self, path: str, **kwargs):
        self.ocr_calls.append({"path": path, **kwargs})
        if self._ocr_error is not None:
            raise self._ocr_error
        pages = self._ocr_pages_by_call.pop(0)
        return SimpleNamespace(pages=list(pages), pages_recommending_hosted=[])


def _stub_engine(monkeypatch, calls: _EngineCalls) -> None:
    monkeypatch.setitem(
        sys.modules,
        "pdf_inspector",
        SimpleNamespace(
            extract_pages_markdown=calls.extract_pages_markdown,
            process_pdf_with_ocr=calls.process_pdf_with_ocr,
        ),
    )


def _inner_metadata(page_count: int, *, pdf_type: str = "mixed", flagged: int = 0) -> dict:
    return {
        "pdf_reader": "pdf_inspector",
        "pdf_type": pdf_type,
        "pdf_confidence": 0.9,
        "page_count": page_count,
        "pages_needing_ocr": flagged,
        "file_name": "doc.pdf",
        "file_path": "/tmp/doc.pdf",
    }


def _page_reader(inner, settings, worker) -> OcrRoutedPdfInspector:
    return OcrRoutedPdfInspector(inner, settings=settings, ocr_client=worker)


def _counts(metadata: dict) -> dict:
    return {
        key: metadata[key]
        for key in (
            "ocr_pages_native",
            "ocr_pages_local",
            "ocr_pages_worker",
            "ocr_pages_unresolved",
        )
    }


# ── Task 4.5c: the merge reaches the emitted document ─────────────────────


def test_only_flagged_pages_are_ocred(monkeypatch, tmp_path, effective_settings):
    """A 20-page file with one flagged page OCRs exactly that page."""
    scan = [_scan_page(i, f"native {i + 1}", i == 9) for i in range(20)]
    engine = _EngineCalls(scan, ocr_pages_by_call=[[_ocr_page(10, "LOCAL ten", 0.9)]])
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="whole", metadata=_inner_metadata(20, flagged=1))
    worker = _FakeWorker()

    docs = _page_reader(
        inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
    ).load_data(tmp_path / "doc.pdf")

    assert len(engine.ocr_calls) == 1
    # The library's scan numbers from 0, the OCR API from 1: page ten is ten.
    assert engine.ocr_calls[0]["page_numbers"] == [10]
    assert worker.calls == []
    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 19,
        "ocr_pages_local": 1,
        "ocr_pages_worker": 0,
        "ocr_pages_unresolved": 0,
    }
    assert meta["ocr_required"] is True
    assert meta["ocr_used"] is True
    # Native pages and one local page both produced text: one string
    # cannot name two engines, so the merge reports mixed (the same rule
    # test_page_merge pins; the local tier is named only when it alone
    # produced the text).
    assert meta["ocr_backend"] == "mixed"
    assert meta["pages_needing_ocr"] == 1
    text = docs[0].text
    assert text.index("native 9") < text.index("LOCAL ten") < text.index("native 11")


def test_a_document_read_wholly_by_local_ocr_names_the_local_tier(
    monkeypatch, tmp_path, effective_settings
):
    """Every page flagged and kept locally: the local tier is the sole producer."""
    scan = [_scan_page(i, "", True) for i in range(2)]
    engine = _EngineCalls(
        scan, ocr_pages_by_call=[[_ocr_page(1, "LOCAL one", 0.9), _ocr_page(2, "LOCAL two", 0.9)]]
    )
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="", metadata=_inner_metadata(2, pdf_type="scanned", flagged=2))
    worker = _FakeWorker()

    docs = _page_reader(
        inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
    ).load_data(tmp_path / "doc.pdf")

    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 0,
        "ocr_pages_local": 2,
        "ocr_pages_worker": 0,
        "ocr_pages_unresolved": 0,
    }
    assert meta["ocr_backend"] == OCR_BACKEND_LOCAL_OCR
    assert docs[0].text == "LOCAL one\n\nLOCAL two"


def test_no_flagged_pages_never_touches_ocr_or_worker(monkeypatch, tmp_path, effective_settings):
    """A clean scan emits native pages only: no OCR call, no worker start."""
    scan = [_scan_page(i, f"native {i + 1}", False) for i in range(4)]
    engine = _EngineCalls(scan, ocr_pages_by_call=[])
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="whole", metadata=_inner_metadata(4, pdf_type="text_based"))
    worker = _FakeWorker()

    docs = _page_reader(
        inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
    ).load_data(tmp_path / "doc.pdf")

    assert engine.ocr_calls == []
    assert worker.calls == []
    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 4,
        "ocr_pages_local": 0,
        "ocr_pages_worker": 0,
        "ocr_pages_unresolved": 0,
    }
    assert meta["ocr_required"] is False
    assert meta["ocr_used"] is False
    assert meta["ocr_backend"] == OCR_BACKEND_FAST_PATH
    assert meta["pages_needing_ocr"] == 0
    assert docs[0].text == "native 1\n\nnative 2\n\nnative 3\n\nnative 4"


# ── Task 4.4: escalation in one request ───────────────────────────────────


def test_unreadable_pages_escalate_alone_in_one_request(monkeypatch, tmp_path, effective_settings):
    """Of three flagged pages the worker receives exactly the two that failed locally."""
    scan = [_scan_page(i, f"native {i + 1}", i + 1 in (2, 5, 7)) for i in range(8)]
    engine = _EngineCalls(
        scan,
        ocr_pages_by_call=[
            [
                _ocr_page(2, "LOCAL two", 0.9),
                _ocr_page(5, "flawed five", 0.3),
                _ocr_page(7, "", None, hosted=True),
            ]
        ],
    )
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="whole", metadata=_inner_metadata(8, flagged=3))
    worker = _FakeWorker(pages_markdown=["WORKER five", "WORKER seven"])

    docs = _page_reader(
        inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
    ).load_data(tmp_path / "doc.pdf")

    assert len(worker.calls) == 1, "escalation is ONE request"
    assert worker.calls[0]["pages"] == [5, 7]
    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 5,
        "ocr_pages_local": 1,
        "ocr_pages_worker": 2,
        "ocr_pages_unresolved": 0,
    }
    assert sum(_counts(meta).values()) == meta["page_count"]
    assert meta["ocr_backend"] == "mixed"
    assert meta["ocr_used"] is True
    text = docs[0].text
    assert text.index("native 4") < text.index("WORKER five") < text.index("native 6")
    assert text.index("native 6") < text.index("WORKER seven") < text.index("native 8")


def test_worker_response_without_pages_markdown_degrades_to_unresolved(
    monkeypatch, tmp_path, effective_settings, caplog
):
    """A worker that cannot attribute per page leaves the escalation unresolved."""
    scan = [_scan_page(i, f"native {i + 1}", i + 1 == 3) for i in range(4)]
    engine = _EngineCalls(scan, ocr_pages_by_call=[[_ocr_page(3, "flawed three", 0.4)]])
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="whole", metadata=_inner_metadata(4, flagged=1))
    worker = _FakeWorker(pages_markdown=None)

    with caplog.at_level("WARNING"):
        docs = _page_reader(
            inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
        ).load_data(tmp_path / "doc.pdf")

    assert len(worker.calls) == 1
    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 3,
        "ocr_pages_local": 0,
        "ocr_pages_worker": 0,
        "ocr_pages_unresolved": 1,
    }
    # The best available text is kept; no marker is inserted.
    assert "flawed three" in docs[0].text
    assert "unavailable" in caplog.text or "attribute" in caplog.text


def test_worker_empty_entry_for_a_page_keeps_best_text_unresolved(
    monkeypatch, tmp_path, effective_settings
):
    """A page the worker also cannot read carries its local text, counted unresolved."""
    scan = [_scan_page(i, f"native {i + 1}", i + 1 == 2) for i in range(3)]
    engine = _EngineCalls(scan, ocr_pages_by_call=[[_ocr_page(2, "flawed two", 0.4)]])
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="whole", metadata=_inner_metadata(3, flagged=1))
    worker = _FakeWorker(pages_markdown=[""])

    docs = _page_reader(
        inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
    ).load_data(tmp_path / "doc.pdf")

    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 2,
        "ocr_pages_local": 0,
        "ocr_pages_worker": 0,
        "ocr_pages_unresolved": 1,
    }
    assert "flawed two" in docs[0].text


# ── Task 4.6: degradation ─────────────────────────────────────────────────


def test_missing_worker_keeps_local_text_and_counts_unresolved(
    monkeypatch, tmp_path, effective_settings, caplog
):
    """An escalated page with no worker keeps its local text, unresolved, no failure."""
    scan = [_scan_page(i, f"native {i + 1}", i + 1 == 4) for i in range(5)]
    engine = _EngineCalls(scan, ocr_pages_by_call=[[_ocr_page(4, "flawed four", 0.4)]])
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="whole", metadata=_inner_metadata(5, flagged=1))
    worker = _FakeWorker(available=False)

    with caplog.at_level("WARNING"):
        docs = _page_reader(
            inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
        ).load_data(tmp_path / "doc.pdf")

    assert worker.calls == []
    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 4,
        "ocr_pages_local": 0,
        "ocr_pages_worker": 0,
        "ocr_pages_unresolved": 1,
    }
    assert "flawed four" in docs[0].text
    assert "worker" in caplog.text.lower()


def test_protocol_1_0_worker_never_receives_a_page_request(
    monkeypatch, tmp_path, effective_settings, caplog
):
    """A worker still on 1.0 degrades the escalation, never sees a 1.1 request.

    Sending the page list would make the old worker reject the envelope
    after dispatch and fail the file. A worker that cannot speak pages
    is, for page routing, a worker that is not there.
    """
    scan = [_scan_page(i, f"native {i + 1}", i + 1 == 4) for i in range(5)]
    engine = _EngineCalls(scan, ocr_pages_by_call=[[_ocr_page(4, "flawed four", 0.4)]])
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="whole", metadata=_inner_metadata(5, flagged=1))
    worker = _FakeWorker(protocol_version="1.0")

    with caplog.at_level("WARNING"):
        docs = _page_reader(
            inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
        ).load_data(tmp_path / "doc.pdf")

    assert worker.calls == [], "no page-listed request may reach a 1.0 worker"
    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 4,
        "ocr_pages_local": 0,
        "ocr_pages_worker": 0,
        "ocr_pages_unresolved": 1,
    }
    assert "flawed four" in docs[0].text
    assert "1.0" in caplog.text and "1.1" in caplog.text


def test_missing_local_runtime_keeps_native_text_and_counts_unresolved(
    monkeypatch, tmp_path, effective_settings, caplog
):
    """No PDFium means flagged pages keep native text, unresolved, with one warning."""
    scan = [_scan_page(i, f"native {i + 1}", i + 1 in (1, 3)) for i in range(4)]
    engine = _EngineCalls(
        scan, ocr_error=ValueError("failed to load PDFium; install a compatible library")
    )
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="whole", metadata=_inner_metadata(4, flagged=2))
    worker = _FakeWorker()

    with caplog.at_level("WARNING"):
        docs = _page_reader(
            inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
        ).load_data(tmp_path / "doc.pdf")

    assert worker.calls == [], "nothing escalates when the local tier never ran"
    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 2,
        "ocr_pages_local": 0,
        "ocr_pages_worker": 0,
        "ocr_pages_unresolved": 2,
    }
    assert meta["ocr_used"] is False
    assert "PDFium" in caplog.text


def test_post_dispatch_worker_failure_fails_the_file(monkeypatch, tmp_path, effective_settings):
    """A worker that fails after accepting the request is a file failure, as today."""
    scan = [_scan_page(i, f"native {i + 1}", i + 1 == 2) for i in range(3)]
    engine = _EngineCalls(scan, ocr_pages_by_call=[[_ocr_page(2, "flawed two", 0.4)]])
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="whole", metadata=_inner_metadata(3, flagged=1))
    worker = _FakeWorker(error=OcrWorkerError("timeout", "no terminal response"))

    reader = _page_reader(
        inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
    )
    with pytest.raises(OcrPostDispatchError) as excinfo:
        reader.load_data(tmp_path / "doc.pdf")
    assert excinfo.value.code == "timeout"


# ── The ADR-066 rescue of last resort ──────────────────────────────────────


def test_rescued_text_survives_when_page_routing_produces_none(
    monkeypatch, tmp_path, effective_settings
):
    """An empty scan keeps the inner reader's rescued text with native counts."""
    scan = [_scan_page(i, "", False) for i in range(2)]
    engine = _EngineCalls(scan, ocr_pages_by_call=[])
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="RESCUED", metadata=_inner_metadata(2, pdf_type="text_based"))
    worker = _FakeWorker()

    docs = _page_reader(
        inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page"), worker
    ).load_data(tmp_path / "doc.pdf")

    assert docs[0].text == "RESCUED"
    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 2,
        "ocr_pages_local": 0,
        "ocr_pages_worker": 0,
        "ocr_pages_unresolved": 0,
    }
    assert meta["ocr_backend"] == OCR_BACKEND_FAST_PATH


# ── Task 5.3: the document unit is unchanged ──────────────────────────────


def test_document_unit_keeps_whole_pdf_behaviour(monkeypatch, tmp_path, effective_settings):
    """The default unit never scans per page and dispatches without a page list."""
    engine = _EngineCalls([], ocr_pages_by_call=[])
    _stub_engine(monkeypatch, engine)
    inner = _FakeInner(text="partial", metadata=_inner_metadata(1, pdf_type="scanned", flagged=1))
    worker = _FakeWorker(pages_markdown=["WORKER one"])

    docs = _page_reader(
        inner, effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="document"), worker
    ).load_data(tmp_path / "doc.pdf")

    assert engine.scan_calls == [], "the document unit takes no page scan"
    assert len(worker.calls) == 1
    assert worker.calls[0]["pages"] is None, "the whole PDF is routed, no page list"
    meta = docs[0].metadata
    assert "ocr_pages_native" not in meta
    assert "ocr_pages_local" not in meta
    assert "ocr_pages_worker" not in meta
    assert "ocr_pages_unresolved" not in meta
    assert meta["ocr_backend"] == "paddleocr_vl"
    assert docs[0].text == "WORKER one"
