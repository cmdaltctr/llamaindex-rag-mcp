"""OCR route dispatch and maths-page routing through the reader seam.

Tasks 4.5, 5.2 and 5.3 of change modular-ocr-workers-dots-mocr. The
scenarios come from ``specs/ocr-worker-engines/spec.md`` ("Every OCR
dispatch SHALL use the primary route, then the fallback route", "OCR
diagnostics SHALL name the answering engine") and
``specs/maths-page-routing/spec.md`` ("Maths pages SHALL route to the
OCR routes", "Maths routing diagnostics SHALL be honest").

Everything external is stubbed: the pdf-inspector scan, its local OCR,
the maths-font detector and both route clients are in-process fakes.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest
from llama_index.core import Document
from llama_index.core.schema import MetadataMode, TextNode

from omrg.core.ingestion.source_state import EXCLUDED_EMBED_METADATA_KEYS, stamp_source_lineage
from omrg.integrations.ocr_worker.client import OcrWorkerError
from omrg.integrations.ocr_worker.protocol import make_success
from omrg.integrations.ocr_worker.routes import OcrRoutes
from omrg.integrations.pdf import maths_routing
from omrg.integrations.pdf.ocr_routing import OcrPostDispatchError, OcrRoutedPdfInspector

pytest.importorskip("pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)")


class _Client:
    """An in-process route client recording every parse request."""

    def __init__(
        self,
        backend_id: str,
        *,
        available: bool = True,
        pages_markdown: dict[int, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.fingerprint = SimpleNamespace(
            available=available, protocol_version="1.1", backend_id=backend_id
        )
        self.calls: list[dict[str, Any]] = []
        self._pages = pages_markdown or {}
        self._error = error

    def parse(self, pdf_path: str, *, pages=None, timeout=None):
        self.calls.append({"pages": list(pages) if pages is not None else None, "timeout": timeout})
        if self._error is not None:
            raise self._error
        if pages is None:
            return make_success(
                "r", f"WHOLE by {self.fingerprint.backend_id}", ocr_backend="x", page_count=1
            )
        texts = [self._pages.get(page, f"{self.fingerprint.backend_id} p{page}") for page in pages]
        return make_success(
            "r",
            "\n\n".join(texts),
            ocr_backend="x",
            page_count=len(pages),
            pages_markdown=texts,
            protocol_version="1.1",
        )


class _Inner:
    def __init__(self, metadata: dict) -> None:
        self._doc = Document(text="partial native text", metadata=dict(metadata))

    def load_data(self, file, *args, **kwargs) -> list:
        return [self._doc]


def _metadata(page_count: int, *, pdf_type: str = "text_based", flagged: int = 0) -> dict:
    return {
        "pdf_reader": "pdf_inspector",
        "pdf_type": pdf_type,
        "pdf_confidence": 0.95,
        "page_count": page_count,
        "pages_needing_ocr": flagged,
    }


def _maths(monkeypatch: pytest.MonkeyPatch, pages: set[int]) -> None:
    """Make the font detector report *pages* as maths pages."""
    monkeypatch.setattr(maths_routing, "maths_font_pages", lambda file: frozenset(pages))


def _scan(monkeypatch: pytest.MonkeyPatch, page_count: int, needs_ocr: set[int]) -> list:
    """Stub the pdf-inspector full scan and local OCR (local tier reads every page)."""
    local_calls: list[list[int]] = []

    def extract_pages_markdown(path: str):
        return SimpleNamespace(
            pages=[
                SimpleNamespace(
                    page=i,
                    markdown=f"native {i + 1}",
                    needs_ocr=(i + 1) in needs_ocr,
                    ocr_reason=None,
                )
                for i in range(page_count)
            ]
        )

    def process_pdf_with_ocr(path: str, **kwargs):
        local_calls.append(list(kwargs["page_numbers"]))
        provenance = SimpleNamespace(
            source="ocr",
            ocr_confidence=0.95,
            ocr_model=SimpleNamespace(name="m", revision="r"),
            hosted_recommended=False,
            warnings=[],
        )
        return SimpleNamespace(
            pages=[
                SimpleNamespace(page_number=p, markdown=f"local {p}", provenance=provenance)
                for p in kwargs["page_numbers"]
            ],
            pages_recommending_hosted=[],
        )

    monkeypatch.setitem(
        sys.modules,
        "pdf_inspector",
        SimpleNamespace(
            extract_pages_markdown=extract_pages_markdown, process_pdf_with_ocr=process_pdf_with_ocr
        ),
    )
    return local_calls


def _read(settings: Any, routes: OcrRoutes, metadata: dict, tmp_path) -> Document:
    reader = OcrRoutedPdfInspector(_Inner(metadata), settings=settings, ocr_client=routes)
    return reader.load_data(tmp_path / "doc.pdf")[0]


def _counts(meta: dict) -> dict:
    return {
        k: meta[k]
        for k in ("ocr_pages_native", "ocr_pages_local", "ocr_pages_worker", "ocr_pages_unresolved")
    }


# ── Every OCR dispatch uses the primary route, then the fallback (4.5) ─────


def test_scanned_pdf_goes_to_the_primary_engine(monkeypatch, tmp_path, effective_settings):
    """Spec: "A scanned PDF goes to the primary engine"; the fallback never runs."""
    _maths(monkeypatch, set())
    primary, fallback = _Client("dots_mocr"), _Client("paddleocr_vl")
    settings = effective_settings(ocr_fallback_enabled=True)
    doc = _read(settings, OcrRoutes(primary, fallback), _metadata(14, pdf_type="scanned"), tmp_path)
    assert doc.text == "WHOLE by dots_mocr"
    assert len(primary.calls) == 1 and primary.calls[0]["pages"] is None
    assert primary.calls[0]["timeout"] == 1680.0, "14 pages x 120 s"
    assert fallback.calls == []
    assert doc.metadata["ocr_backend"] == "dots_mocr"


def test_missing_primary_hands_the_whole_pdf_to_the_fallback(
    monkeypatch, tmp_path, effective_settings
):
    """Spec: "A missing primary engine hands the request to the fallback"."""
    _maths(monkeypatch, set())
    primary = _Client("dots_mocr", available=False)
    fallback = _Client("paddleocr_vl")
    settings = effective_settings(ocr_fallback_enabled=True)
    doc = _read(settings, OcrRoutes(primary, fallback), _metadata(3, pdf_type="scanned"), tmp_path)
    assert doc.text == "WHOLE by paddleocr_vl"
    assert primary.calls == []
    assert doc.metadata["ocr_backend"] == "paddleocr_vl", "the fallback names itself"


def test_post_dispatch_failure_does_not_retry_on_the_fallback(
    monkeypatch, tmp_path, effective_settings
):
    """Spec: "Post-dispatch failure does not retry on the fallback"."""
    _maths(monkeypatch, set())
    primary = _Client("dots_mocr", error=OcrWorkerError("worker_crashed", "exit 9"))
    fallback = _Client("paddleocr_vl")
    settings = effective_settings(ocr_fallback_enabled=True)
    with pytest.raises(OcrPostDispatchError) as excinfo:
        _read(settings, OcrRoutes(primary, fallback), _metadata(2, pdf_type="scanned"), tmp_path)
    assert excinfo.value.code == "worker_crashed"
    assert fallback.calls == []


def test_no_route_keeps_partial_text(monkeypatch, tmp_path, effective_settings):
    """Both routes unavailable: the existing degraded behaviour applies."""
    _maths(monkeypatch, set())
    routes = OcrRoutes(_Client("a", available=False), _Client("b", available=False))
    settings = effective_settings(ocr_fallback_enabled=True)
    doc = _read(settings, routes, _metadata(2, pdf_type="scanned"), tmp_path)
    assert doc.text == "partial native text"
    assert doc.metadata["ocr_required"] is True and doc.metadata["ocr_used"] is False


def test_page_unit_escalation_uses_the_fallback_when_primary_is_missing(
    monkeypatch, tmp_path, effective_settings
):
    """Escalated pages follow the same route selection, and name the fallback."""
    _maths(monkeypatch, set())
    _scan(monkeypatch, 3, needs_ocr=set())
    primary = _Client("dots_mocr", available=False)
    fallback = _Client("paddleocr_vl")
    settings = effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page")
    routes = OcrRoutes(primary, fallback)
    _maths(monkeypatch, {2})
    doc = _read(settings, routes, _metadata(3), tmp_path)
    assert fallback.calls == [{"pages": [2], "timeout": 300.0}]
    assert doc.metadata["ocr_backend"] == "mixed"
    assert "paddleocr_vl p2" in doc.text


# ── Maths pages route to the OCR routes (5.2) ──────────────────────────────


def test_only_maths_pages_go_to_the_primary_engine(monkeypatch, tmp_path, effective_settings):
    """Spec: 12 pages, 4 flagged maths pages, none needing OCR: one request of 4."""
    local_calls = _scan(monkeypatch, 12, needs_ocr=set())
    _maths(monkeypatch, {2, 5, 7, 11})
    primary, fallback = _Client("dots_mocr"), _Client("paddleocr_vl")
    settings = effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page")
    doc = _read(settings, OcrRoutes(primary, fallback), _metadata(12), tmp_path)
    assert [c["pages"] for c in primary.calls] == [[2, 5, 7, 11]]
    assert fallback.calls == []
    assert local_calls == [], "the local tier does not process maths pages"
    assert _counts(doc.metadata) == {
        "ocr_pages_native": 8,
        "ocr_pages_local": 0,
        "ocr_pages_worker": 4,
        "ocr_pages_unresolved": 0,
    }
    assert "native 1" in doc.text and "dots_mocr p5" in doc.text
    assert doc.metadata["pages_maths_font"] == 4
    assert doc.metadata["ocr_backend"] == "mixed"


def test_a_page_both_maths_and_needing_ocr_is_sent_once(monkeypatch, tmp_path, effective_settings):
    """A maths page that also needs OCR goes once, in the one request."""
    local_calls = _scan(monkeypatch, 4, needs_ocr={1, 3})
    _maths(monkeypatch, {3})
    primary = _Client("dots_mocr")
    settings = effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page")
    doc = _read(settings, OcrRoutes(primary), _metadata(4), tmp_path)
    assert local_calls == [[1]]
    assert [c["pages"] for c in primary.calls] == [[3]]
    assert sum(_counts(doc.metadata).values()) == 4


def test_missing_primary_sends_maths_pages_to_the_fallback(
    monkeypatch, tmp_path, effective_settings
):
    """Spec: "A missing primary engine falls back" — the 4 pages in one request."""
    _scan(monkeypatch, 12, needs_ocr=set())
    _maths(monkeypatch, {1, 2, 3, 4})
    primary = _Client("dots_mocr", available=False)
    fallback = _Client("paddleocr_vl")
    settings = effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page")
    _read(settings, OcrRoutes(primary, fallback), _metadata(12), tmp_path)
    assert [c["pages"] for c in fallback.calls] == [[1, 2, 3, 4]]


def test_no_engine_keeps_native_text_for_maths_pages(monkeypatch, tmp_path, effective_settings):
    """Spec: "No engine keeps native text"; the pages count unresolved."""
    _scan(monkeypatch, 6, needs_ocr=set())
    _maths(monkeypatch, {1, 2, 3, 4})
    settings = effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page")
    doc = _read(settings, OcrRoutes(_Client("a", available=False)), _metadata(6), tmp_path)
    assert _counts(doc.metadata)["ocr_pages_unresolved"] == 4
    assert "native 1" in doc.text and "native 4" in doc.text


def test_empty_engine_page_keeps_native_text(monkeypatch, tmp_path, effective_settings):
    """An engine's empty Markdown for a maths page keeps native text, unresolved."""
    _scan(monkeypatch, 3, needs_ocr=set())
    _maths(monkeypatch, {2, 3})
    primary = _Client("dots_mocr", pages_markdown={2: ""})
    settings = effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page")
    doc = _read(settings, OcrRoutes(primary), _metadata(3), tmp_path)
    assert _counts(doc.metadata) == {
        "ocr_pages_native": 1,
        "ocr_pages_local": 0,
        "ocr_pages_worker": 1,
        "ocr_pages_unresolved": 1,
    }
    assert "native 2" in doc.text


def test_document_unit_sends_a_maths_paper_whole(monkeypatch, tmp_path, effective_settings):
    """Spec: 14 pages, 9 flagged, default fraction: the whole PDF goes to the primary."""
    _maths(monkeypatch, set(range(1, 10)))
    primary = _Client("dots_mocr")
    settings = effective_settings(ocr_fallback_enabled=True)
    assert settings.ocr_maths_page_fraction == 0.10
    doc = _read(settings, OcrRoutes(primary), _metadata(14), tmp_path)
    assert [c["pages"] for c in primary.calls] == [None]
    assert doc.text == "WHOLE by dots_mocr"
    assert doc.metadata["pages_maths_font"] == 9


def test_document_unit_keeps_few_maths_pages_on_the_fast_path(
    monkeypatch, tmp_path, effective_settings
):
    """Spec: 40 pages, 1 flagged, gate not selected: no request."""
    _maths(monkeypatch, {7})
    primary = _Client("dots_mocr")
    settings = effective_settings(ocr_fallback_enabled=True)
    doc = _read(settings, OcrRoutes(primary), _metadata(40), tmp_path)
    assert primary.calls == []
    assert doc.metadata["ocr_used"] is False
    assert doc.metadata["pages_maths_font"] == 1


def test_zero_fraction_disables_the_document_condition(monkeypatch, tmp_path, effective_settings):
    """``OCR_MATHS_PAGE_FRACTION=0.0`` never selects a PDF for its maths pages."""
    _maths(monkeypatch, set(range(1, 15)))
    primary = _Client("dots_mocr")
    settings = effective_settings(ocr_fallback_enabled=True, ocr_maths_page_fraction=0.0)
    _read(settings, OcrRoutes(primary), _metadata(14), tmp_path)
    assert primary.calls == []


def test_fraction_is_read_from_injected_settings(monkeypatch, tmp_path, effective_settings):
    """Spec: the fraction comes from the injected settings (3 of 14 is 0.21)."""
    _maths(monkeypatch, {1, 2, 3})
    high, low = _Client("dots_mocr"), _Client("dots_mocr")
    _read(
        effective_settings(ocr_fallback_enabled=True, ocr_maths_page_fraction=0.25),
        OcrRoutes(high),
        _metadata(14),
        tmp_path,
    )
    _read(
        effective_settings(ocr_fallback_enabled=True, ocr_maths_page_fraction=0.20),
        OcrRoutes(low),
        _metadata(14),
        tmp_path,
    )
    assert high.calls == [] and len(low.calls) == 1


def test_disabled_maths_routing_changes_nothing(monkeypatch, tmp_path, effective_settings):
    """Spec: "Disabled maths routing changes nothing"; the detector never runs."""

    def forbidden(file):
        raise AssertionError("detector must not run when maths routing is off")

    monkeypatch.setattr(maths_routing, "maths_font_pages", forbidden)
    local_calls = _scan(monkeypatch, 4, needs_ocr=set())
    primary = _Client("dots_mocr")
    for unit in ("document", "page"):
        settings = effective_settings(
            ocr_fallback_enabled=True, ocr_maths_routing_enabled=False, ocr_routing_unit=unit
        )
        doc = _read(settings, OcrRoutes(primary), _metadata(4), tmp_path)
        assert "pages_maths_font" not in doc.metadata
    assert primary.calls == [] and local_calls == []


# ── Diagnostics stay out of embedded text (5.3) ────────────────────────────


def test_page_unit_counts_sum_and_backend_is_mixed(monkeypatch, tmp_path, effective_settings):
    """Spec: native plus primary-route maths pages report ``mixed``; counts sum."""
    _scan(monkeypatch, 5, needs_ocr={4})
    _maths(monkeypatch, {1})
    settings = effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page")
    doc = _read(settings, OcrRoutes(_Client("dots_mocr")), _metadata(5), tmp_path)
    assert doc.metadata["ocr_backend"] == "mixed"
    assert sum(_counts(doc.metadata).values()) == doc.metadata["page_count"] == 5


def test_maths_page_count_does_not_reach_embeddings() -> None:
    """Spec: "The maths-page count does not reach embeddings" (nor LLM text)."""
    assert "pages_maths_font" in EXCLUDED_EMBED_METADATA_KEYS
    node = TextNode(text="Equation text.", metadata={"pages_maths_font": 9, "ocr_backend": "mixed"})
    stamp_source_lineage(
        [node],
        file_path="/fixtures/maths.pdf",
        source_id="src-maths",
        content_hash="a" * 64,
        index_identity="b" * 64,
        source_version="c" * 64,
        source_attempt="attempt-1",
    )
    assert node.metadata["pages_maths_font"] == 9
    for mode in (MetadataMode.EMBED, MetadataMode.LLM):
        assert "pages_maths_font" not in node.get_content(metadata_mode=mode)
