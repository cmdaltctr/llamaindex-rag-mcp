"""Local OCR tier and its escalation post-check (tasks 4.2 and 4.2a).

Tier 1 of the ``page`` routing unit: pdf-inspector's selective OCR
(``process_pdf_with_ocr`` in ``force`` mode) on exactly the flagged pages,
then the post-check that decides which pages escalate to the PaddleOCR-VL
worker. Escalation is decided AFTER the attempt, on design decision 4 of
change page-level-ocr-routing: empty or whitespace-only output, confidence
below ``OCR_LOCAL_MIN_CONFIDENCE``, or ``hosted_recommended``. No script or
typography pre-check exists, and none may be added without measurement
(task 2.3 stays deferred).

Also covers the identity plumbing that arrived with the tier: the resolved
local model identity (``name@revision``) joins the index identity payload
only under the ``page`` unit, and the resolution probe runs only when the
tier can actually run.

The library is stubbed in ``sys.modules``; nothing parses a real PDF and
nothing loads a real model.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from omrg.core.ingestion.ocr_identity import ocr_routing_payload, resolved_routing_payload
from omrg.integrations.pdf import page_routing
from omrg.integrations.pdf.page_routing import local_ocr


def _provenance(
    *,
    source: str = "ocr",
    confidence: float | None = 0.9,
    hosted: bool = False,
    model: tuple[str, str] | None = ("pp-ocrv6-small", "oar-ocr-v0.7.0"),
    warnings: list[str] | None = None,
):
    """Return one ``OcrPageProvenance`` stand-in with the fields the tier reads."""
    return SimpleNamespace(
        source=source,
        ocr_confidence=confidence,
        ocr_model=SimpleNamespace(name=model[0], revision=model[1]) if model else None,
        hosted_recommended=hosted,
        warnings=warnings or [],
    )


def _ocr_page(page: int, markdown: str, provenance) -> SimpleNamespace:
    """Return one ``OcrPageResult`` stand-in, numbered from 1 as the library does."""
    return SimpleNamespace(page_number=page, markdown=markdown, provenance=provenance)


class _Calls:
    """Recording stub for ``pdf_inspector.process_pdf_with_ocr``."""

    def __init__(self, results_by_call):
        self.calls: list[dict] = []
        self._results_by_call = list(results_by_call)

    def __call__(self, path, **kwargs):
        self.calls.append({"path": path, **kwargs})
        result = self._results_by_call.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _stub_process(monkeypatch, calls: _Calls):
    """Install a pdf_inspector stub whose OCR entry point records and replays."""
    monkeypatch.setitem(
        sys.modules,
        "pdf_inspector",
        SimpleNamespace(process_pdf_with_ocr=calls),
    )
    return calls


# ── The tier call (task 4.2) ───────────────────────────────────────────────


def test_force_mode_ocrs_exactly_the_flagged_pages(monkeypatch, tmp_path, effective_settings):
    """Force mode with the 1-based page list: the library never re-routes."""
    calls = _Calls(
        [
            SimpleNamespace(
                pages=[
                    _ocr_page(3, "page three", _provenance()),
                    _ocr_page(7, "page seven", _provenance()),
                ]
            )
        ]
    )
    _stub_process(monkeypatch, calls)

    results = local_ocr(tmp_path / "doc.pdf", [7, 3], settings=effective_settings())

    assert len(calls.calls) == 1
    assert calls.calls[0]["mode"] == "force"
    assert calls.calls[0]["page_numbers"] == [3, 7]
    assert [r.page for r in results] == [3, 7]


def test_model_directory_and_offline_come_from_settings(monkeypatch, tmp_path, effective_settings):
    """An empty directory means the library default cache; offline passes through."""
    calls = _Calls(
        [
            SimpleNamespace(pages=[_ocr_page(1, "text", _provenance())]),
            SimpleNamespace(pages=[_ocr_page(1, "text", _provenance())]),
        ]
    )
    _stub_process(monkeypatch, calls)

    local_ocr(
        tmp_path / "doc.pdf",
        [1],
        settings=effective_settings(ocr_local_model_directory="", ocr_local_offline=False),
    )
    local_ocr(
        tmp_path / "doc.pdf",
        [1],
        settings=effective_settings(
            ocr_local_model_directory="/models/leaf", ocr_local_offline=True
        ),
    )

    assert calls.calls[0]["model_directory"] is None
    assert calls.calls[0]["offline"] is False
    assert calls.calls[1]["model_directory"] == "/models/leaf"
    assert calls.calls[1]["offline"] is True


def test_engine_confidence_knobs_stay_at_library_defaults(
    monkeypatch, tmp_path, effective_settings
):
    """The engine's own confidence parameters were never measured; ours is a post-check.

    Experiment 33 task 6.7 called the library with its defaults and applied
    the 0.8 cut to the returned provenance. Passing the cut into the engine
    would run unmeasured behaviour.
    """
    calls = _Calls([SimpleNamespace(pages=[_ocr_page(1, "text", _provenance())])])
    _stub_process(monkeypatch, calls)

    local_ocr(tmp_path / "doc.pdf", [1], settings=effective_settings())

    assert "minimum_confidence" not in calls.calls[0]
    assert "hosted_recommendation_confidence" not in calls.calls[0]


def test_no_flagged_pages_means_no_library_call(monkeypatch, tmp_path, effective_settings):
    """An empty page list skips the engine: nothing to OCR, no model load."""
    calls = _Calls([])
    _stub_process(monkeypatch, calls)

    assert local_ocr(tmp_path / "doc.pdf", [], settings=effective_settings()) == []
    assert calls.calls == []


def test_page_reports_text_confidence_and_model(monkeypatch, tmp_path, effective_settings):
    """A readable page carries its text, confidence and resolved model identity."""
    calls = _Calls(
        [
            SimpleNamespace(
                pages=[_ocr_page(2, "read text", _provenance(confidence=0.93, model=("m", "r1")))]
            )
        ]
    )
    _stub_process(monkeypatch, calls)

    result = local_ocr(tmp_path / "doc.pdf", [2], settings=effective_settings())[0]

    assert result.text == "read text"
    assert result.confidence == 0.93
    assert result.model == "m@r1"


# ── The escalation post-check (task 4.2a) ──────────────────────────────────


def test_readable_page_does_not_escalate(monkeypatch, tmp_path, effective_settings):
    """Text present, confidence at or above the cut, no hosted flag: tier 1 keeps it."""
    calls = _Calls(
        [
            SimpleNamespace(
                pages=[
                    _ocr_page(1, "readable", _provenance(confidence=0.8)),
                ]
            )
        ]
    )
    _stub_process(monkeypatch, calls)

    result = local_ocr(tmp_path / "doc.pdf", [1], settings=effective_settings())[0]

    assert result.escalates is False
    assert result.reasons == ()


def test_empty_text_escalates(monkeypatch, tmp_path, effective_settings):
    """Empty output is the class the packaged model cannot read at all."""
    calls = _Calls([SimpleNamespace(pages=[_ocr_page(1, "", _provenance(confidence=0.95))])])
    _stub_process(monkeypatch, calls)

    result = local_ocr(tmp_path / "doc.pdf", [1], settings=effective_settings())[0]

    assert result.escalates is True
    assert "empty_text" in result.reasons


def test_whitespace_only_text_escalates(monkeypatch, tmp_path, effective_settings):
    """Whitespace is no text: the scenario the experiment's empty-output rule catches."""
    calls = _Calls([SimpleNamespace(pages=[_ocr_page(1, " \n\t ", _provenance(confidence=0.95))])])
    _stub_process(monkeypatch, calls)

    result = local_ocr(tmp_path / "doc.pdf", [1], settings=effective_settings())[0]

    assert result.escalates is True
    assert "empty_text" in result.reasons


def test_confidence_below_the_cut_escalates(monkeypatch, tmp_path, effective_settings):
    """The calibrated 0.8 cut: below it, the worker rereads the page."""
    calls = _Calls(
        [SimpleNamespace(pages=[_ocr_page(1, "confident enough?", _provenance(confidence=0.79))])]
    )
    _stub_process(monkeypatch, calls)

    result = local_ocr(tmp_path / "doc.pdf", [1], settings=effective_settings())[0]

    assert result.escalates is True
    assert "low_confidence" in result.reasons


def test_missing_confidence_escalates(monkeypatch, tmp_path, effective_settings):
    """No reported confidence cannot vouch for the text; the experiment treated it as 0.

    The blank-page case: the engine reports no confidence together with no
    usable text and a hosted recommendation.
    """
    calls = _Calls(
        [SimpleNamespace(pages=[_ocr_page(1, "some text", _provenance(confidence=None))])]
    )
    _stub_process(monkeypatch, calls)

    result = local_ocr(tmp_path / "doc.pdf", [1], settings=effective_settings())[0]

    assert result.escalates is True
    assert "low_confidence" in result.reasons


def test_missing_page_in_result_escalates(monkeypatch, tmp_path, effective_settings):
    """A requested page the engine never reported produced nothing: escalate it."""
    calls = _Calls([SimpleNamespace(pages=[_ocr_page(4, "reported", _provenance())])])
    _stub_process(monkeypatch, calls)

    results = {
        r.page: r for r in local_ocr(tmp_path / "doc.pdf", [4, 9], settings=effective_settings())
    }

    assert results[9].escalates is True
    assert results[9].text == ""
    assert "missing_page" in results[9].reasons
    assert results[4].escalates is False


def test_hosted_recommendation_escalates_even_with_high_confidence(
    monkeypatch, tmp_path, effective_settings
):
    """The engine's own hosted flag costs nothing and fired on no page at recall >= 0.8."""
    calls = _Calls(
        [
            SimpleNamespace(
                pages=[
                    _ocr_page(1, "fluent but flagged", _provenance(confidence=0.95, hosted=True))
                ]
            )
        ]
    )
    _stub_process(monkeypatch, calls)

    result = local_ocr(tmp_path / "doc.pdf", [1], settings=effective_settings())[0]

    assert result.escalates is True
    assert "hosted_recommended" in result.reasons


def test_reasons_accumulate(monkeypatch, tmp_path, effective_settings):
    """One page can fire several conditions; the wiring sends it once either way."""
    calls = _Calls(
        [SimpleNamespace(pages=[_ocr_page(1, "", _provenance(confidence=0.1, hosted=True))])]
    )
    _stub_process(monkeypatch, calls)

    result = local_ocr(tmp_path / "doc.pdf", [1], settings=effective_settings())[0]

    assert set(result.reasons) == {"empty_text", "low_confidence", "hosted_recommended"}


def test_escalation_cut_comes_from_settings_not_a_constant(
    monkeypatch, tmp_path, effective_settings
):
    """The threshold is injected configuration; the module holds no constant."""
    calls = _Calls(
        [
            SimpleNamespace(pages=[_ocr_page(1, "borderline", _provenance(confidence=0.75))]),
            SimpleNamespace(pages=[_ocr_page(1, "borderline", _provenance(confidence=0.75))]),
        ]
    )
    _stub_process(monkeypatch, calls)

    at_default = local_ocr(
        tmp_path / "doc.pdf", [1], settings=effective_settings(ocr_local_min_confidence=0.8)
    )[0]
    raised = local_ocr(
        tmp_path / "doc.pdf", [1], settings=effective_settings(ocr_local_min_confidence=0.7)
    )[0]

    assert at_default.escalates is True
    assert raised.escalates is False


# ── The resolved model identity in the index identity payload ──────────────


def test_payload_gains_the_model_only_when_resolved_and_page_unit(effective_settings):
    """local_tier.model appears with a resolved identity under the page unit."""
    page = effective_settings(ocr_routing_unit="page")

    with_model = ocr_routing_payload(page, local_model_identity="pp-ocrv6-small@oar-ocr-v0.7.0")
    unresolved = ocr_routing_payload(page, local_model_identity=None)

    assert with_model["local_tier"] == {
        "min_confidence": 0.8,
        "model": "pp-ocrv6-small@oar-ocr-v0.7.0",
    }
    # Absence means unresolved (runtime missing): the identity moves when it
    # appears, which is correct, because the tier's text changes with it.
    assert unresolved["local_tier"] == {"min_confidence": 0.8}


def test_document_unit_ignores_a_resolved_model(effective_settings):
    """A document-unit install hashes exactly what it hashed; no local tier exists."""
    document = effective_settings(ocr_routing_unit="document")

    payload = ocr_routing_payload(document, local_model_identity="pp-ocrv6-small@oar-ocr-v0.7.0")

    assert "local_tier" not in payload
    assert "routing_unit" not in payload


def test_resolved_payload_probes_only_when_the_tier_can_run(monkeypatch, effective_settings):
    """The probe runs for page unit with the fallback enabled, and only then."""
    probed: list[dict] = []

    def _probe(settings):
        probed.append({"offline": settings.ocr_local_offline})
        return "m@r1"

    monkeypatch.setattr(page_routing, "resolve_local_model_identity", _probe)

    resolved_routing_payload(effective_settings(ocr_routing_unit="document"))
    resolved_routing_payload(
        effective_settings(ocr_routing_unit="page", ocr_fallback_enabled=False)
    )

    assert probed == []

    payload = resolved_routing_payload(
        effective_settings(ocr_routing_unit="page", ocr_fallback_enabled=True)
    )

    assert probed == [{"offline": False}]
    assert payload["local_tier"] == {"min_confidence": 0.8, "model": "m@r1"}


# ── The resolution probe itself ────────────────────────────────────────────


@pytest.fixture()
def _clean_resolution_cache(monkeypatch):
    """Start and end each probe test with an empty process cache."""
    page_routing.reset_local_model_resolution()
    yield
    page_routing.reset_local_model_resolution()


def _probe_stub(page_number, markdown, provenance):
    return SimpleNamespace(pages=[SimpleNamespace(page_number=page_number, provenance=provenance)])


def test_probe_resolves_name_at_revision(
    monkeypatch, tmp_path, effective_settings, _clean_resolution_cache
):
    """The probe reads the model identity off a blank page's provenance."""
    calls = _Calls(
        [
            _probe_stub(
                1,
                "",
                _provenance(
                    confidence=None, hosted=True, model=("pp-ocrv6-small", "oar-ocr-v0.7.0")
                ),
            )
        ]
    )
    _stub_process(monkeypatch, calls)

    identity = page_routing.resolve_local_model_identity(effective_settings())

    assert identity == "pp-ocrv6-small@oar-ocr-v0.7.0"
    assert len(calls.calls) == 1
    # The probe is a one-page force attempt on a generated blank PDF.
    assert calls.calls[0]["mode"] == "force"
    assert calls.calls[0]["page_numbers"] == [1]
    assert calls.calls[0]["path"].endswith(".pdf")


def test_probe_applies_the_model_settings(
    monkeypatch, tmp_path, effective_settings, _clean_resolution_cache
):
    """The probe must resolve the same model the tier would use."""
    calls = _Calls([_probe_stub(1, "", _provenance())])
    _stub_process(monkeypatch, calls)

    page_routing.resolve_local_model_identity(
        effective_settings(ocr_local_model_directory="/models/leaf", ocr_local_offline=True)
    )

    assert calls.calls[0]["model_directory"] == "/models/leaf"
    assert calls.calls[0]["offline"] is True


def test_probe_result_is_cached_per_process(
    monkeypatch, effective_settings, _clean_resolution_cache
):
    """One probe per process: a second resolution costs nothing."""
    calls = _Calls([_probe_stub(1, "", _provenance())])
    _stub_process(monkeypatch, calls)

    first = page_routing.resolve_local_model_identity(effective_settings())
    second = page_routing.resolve_local_model_identity(effective_settings())

    assert first == second == "pp-ocrv6-small@oar-ocr-v0.7.0"
    assert len(calls.calls) == 1


def test_probe_failure_resolves_to_none_with_a_warning(
    monkeypatch, effective_settings, _clean_resolution_cache, caplog
):
    """A missing runtime is a stable unresolved state, not an exception past the boundary.

    The identity then omits the model, and gains it when the runtime
    appears, which reindexes exactly when the emitted text would change.
    """
    calls = _Calls([ValueError("failed to load PDFium; install a compatible library")])
    _stub_process(monkeypatch, calls)

    with caplog.at_level("WARNING"):
        identity = page_routing.resolve_local_model_identity(effective_settings())

    assert identity is None
    assert "PDFium" in caplog.text


def test_an_unresolved_runtime_is_reprobed(
    monkeypatch, effective_settings, _clean_resolution_cache
):
    """A failed probe caches nothing: the next call gains the identity.

    A cached ``None`` would keep the identity absent after the runtime
    appeared, so changed content would be treated as unchanged.
    """
    calls = _Calls(
        [
            ValueError("failed to load PDFium; install a compatible library"),
            _probe_stub(1, "", _provenance()),
        ]
    )
    _stub_process(monkeypatch, calls)

    first = page_routing.resolve_local_model_identity(effective_settings())
    second = page_routing.resolve_local_model_identity(effective_settings())

    assert first is None
    assert second == "pp-ocrv6-small@oar-ocr-v0.7.0"
    assert len(calls.calls) == 2


def test_probe_cache_is_scoped_by_the_model_settings(
    monkeypatch, effective_settings, _clean_resolution_cache
):
    """A different model directory or offline mode resolves afresh.

    The pair is what ``local_ocr`` feeds the engine, so each pair owns
    its own cache entry: one model's identity must never vouch for
    another's text.
    """
    calls = _Calls(
        [
            _probe_stub(1, "", _provenance(model=("model-a", "r1"))),
            _probe_stub(1, "", _provenance(model=("model-b", "r2"))),
        ]
    )
    _stub_process(monkeypatch, calls)

    default = page_routing.resolve_local_model_identity(effective_settings())
    other = page_routing.resolve_local_model_identity(
        effective_settings(ocr_local_model_directory="/models/other", ocr_local_offline=True)
    )
    # The second probe ran under the pair the tier would use.
    assert calls.calls[1]["model_directory"] == "/models/other"
    assert calls.calls[1]["offline"] is True

    assert default == "model-a@r1"
    assert other == "model-b@r2"


def test_a_page_without_model_identity_reports_none(
    monkeypatch, effective_settings, _clean_resolution_cache
):
    """A provenance without a model cannot name one; the probe says so, not a guess."""
    calls = _Calls([_probe_stub(1, "", _provenance(model=None))])
    _stub_process(monkeypatch, calls)

    assert page_routing.resolve_local_model_identity(effective_settings()) is None
