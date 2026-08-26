"""Fast harness tests for the repaired Experiment 14 build path (D19).

Task 4.3.6 + 4.3.7 agreement tests.  No network, no Ollama, no Chroma
store: parsing uses pypdf only (deterministic per AGENTS.md gotcha 6)
over the two immutable fixture PDFs copied byte-identical from
``tests/fixtures/pdf_dir/``.  The runner scripts are loaded via importlib
because the experiment directory name starts with a digit.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from experiments._lib.plan import ExperimentPlan
from experiments._lib.preflight import (
    PreflightError,
    assert_parser_invoked_before_embeddings,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXP14_DIR = REPO_ROOT / "experiments" / "14-liteparse-qasper-promotion-2026-06-29"
FIXTURES_DIR = EXP14_DIR / "fixtures"
PLAN_PATH = EXP14_DIR / "plan.json"
BUILD_INDEXES_PATH = EXP14_DIR / "build_indexes.py"
RUN_EVAL_PATH = EXP14_DIR / "run_eval.py"


def _load_module(name: str, path: Path) -> ModuleType:
    """Load a runner script as a module (digit-leading directory name)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exp14 = _load_module("exp14_build", BUILD_INDEXES_PATH)
run_eval = _load_module("exp14_run_eval", RUN_EVAL_PATH)


def test_audit_substrings_present() -> None:
    """Mirror of the frozen audit test: real PDF glob + production factory."""
    source = BUILD_INDEXES_PATH.read_text(encoding="utf-8")
    assert 'glob("*.pdf")' in source
    assert "get_pdf_reader" in source


def test_corpus_identity_stable_and_file_listed() -> None:
    first = exp14.corpus_identity(FIXTURES_DIR)
    second = exp14.corpus_identity(FIXTURES_DIR)
    assert first == second
    assert first["files"] == ["doc1_climate.pdf", "doc2_quantum.pdf"]
    expected_doc1 = hashlib.sha256((FIXTURES_DIR / "doc1_climate.pdf").read_bytes()).hexdigest()
    assert first["sha256_by_file"]["doc1_climate.pdf"] == expected_doc1
    assert first["corpus_sha256"].startswith("sha256:")


def test_parse_corpus_real_pdf_bytes() -> None:
    result = exp14.parse_corpus(FIXTURES_DIR, "pypdf")
    assert result["reader"] == "pypdf"
    assert [doc["file"] for doc in result["parsed_documents"]] == [
        "doc1_climate.pdf",
        "doc2_quantum.pdf",
    ]
    for doc in result["parsed_documents"]:
        # The fixtures contain extractable text (verified against pypdf).
        assert doc["text"] != ""
        assert doc["char_count"] == len(doc["text"]) > 0
        assert doc["parse_time_s"] >= 0
        assert doc["error"] is None
        assert doc["source_page_count"] > 0
        assert doc["emitted_document_count"] > 0
        assert doc["token_count"] > 0
        assert (
            doc["source_sha256"]
            == hashlib.sha256((FIXTURES_DIR / doc["file"]).read_bytes()).hexdigest()
        )

    kinds_by_file: dict[str, list[str]] = {}
    for event in result["events"]:
        kinds_by_file.setdefault(event["file"], []).append(event["event"])
    for name in ("doc1_climate.pdf", "doc2_quantum.pdf"):
        assert kinds_by_file[name][0] == "parse_start"
        assert kinds_by_file[name][-1] == "parse_end"

    assert result["artefact_sha256"].startswith("sha256:")
    assert (
        result["parsed_text_sha256_by_file"]["doc1_climate.pdf"]
        == hashlib.sha256(result["parsed_documents"][0]["text"].encode("utf-8")).hexdigest()
    )


def test_parser_invoked_before_embeddings_preflight() -> None:
    late_parse_events = [
        {"event": "embed_start", "timestamp": 1.0},
        {
            "event": "parse_start",
            "parser": "pypdf",
            "file": "doc1_climate.pdf",
            "timestamp": 2.0,
        },
        {"event": "parse_end", "parser": "pypdf", "file": "doc1_climate.pdf", "timestamp": 3.0},
    ]
    with pytest.raises(PreflightError):
        assert_parser_invoked_before_embeddings(late_parse_events, ["pypdf"])

    result = exp14.parse_corpus(FIXTURES_DIR, "pypdf")
    # Real parse events carry no embed events: vacuous ordering, but the
    # declared parser must have recorded parse_start for every file.
    assert_parser_invoked_before_embeddings(result["events"], ["pypdf"])


def test_preflight_check_passes_for_pypdf() -> None:
    parse_result = exp14.parse_corpus(FIXTURES_DIR, "pypdf")
    manifest = exp14.preflight_check(parse_result, embed_model="nomic-embed-text")
    assert manifest["document_backend"]["requested"] == "pypdf"
    assert manifest["document_backend"]["effective"] == "pypdf"
    assert manifest["embedding"]["model"] == "nomic-embed-text"
    assert manifest["experiment_id"] == "14-liteparse-qasper-promotion"
    assert manifest["protocol_version"] == "2.1"
    assert manifest["corpus_identity"] == parse_result["corpus_identity"]["corpus_sha256"]
    # The directory-level corpus identity was supplied via ``extra``; the
    # stale single-path null reason must not survive.
    assert "corpus_identity" not in manifest["null_reasons"]


def test_artefact_identity_differs_when_text_differs() -> None:
    result = exp14.parse_corpus(FIXTURES_DIR, "pypdf")
    base_identity = result["artefact_sha256"]
    assert exp14.artefact_identity(result["parsed_documents"]) == base_identity

    perturbed = [dict(doc) for doc in result["parsed_documents"]]
    perturbed[0]["text"] = perturbed[0]["text"] + " perturbed"
    assert exp14.artefact_identity(perturbed) != base_identity


def test_plan_agrees_with_build_cells() -> None:
    payload = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan = ExperimentPlan.from_json(PLAN_PATH)

    build_cells = exp14.build_cell_matrix()
    assert len(build_cells) == 3
    # A plan restricted to the generator's cells must accept exactly those
    # cells (this also validates factor names/levels against the declared
    # manipulated factors).
    build_only = ExperimentPlan.from_dict({**payload, "cells": build_cells})
    build_only.assert_runner_cells(build_cells)

    eval_cells = run_eval.build_eval_cell_matrix()
    assert len(eval_cells) == 6
    eval_only = ExperimentPlan.from_dict({**payload, "cells": eval_cells})
    eval_only.assert_runner_cells(eval_cells)

    # The full plan declares exactly the union of both pure generators.
    plan_by_id = {cell.id: dict(cell.factors) for cell in plan.cells}
    generated_by_id = {cell["id"]: cell["factors"] for cell in [*build_cells, *eval_cells]}
    assert plan_by_id == generated_by_id
    assert set(plan_by_id) == {
        "build_pypdf",
        "build_liteparse",
        "build_pdf_inspector",
        "pypdf_off",
        "pypdf_on",
        "liteparse_off",
        "liteparse_on",
        "pdf_inspector_off",
        "pdf_inspector_on",
    }
    # The rerank factor levels are the plan's booleans, not strings.
    assert plan.manipulated_factors["rerank"] == (False, True)


def test_write_parsed_artefact_atomic(tmp_path: Path) -> None:
    result = exp14.parse_corpus(FIXTURES_DIR, "pypdf")
    path = exp14.write_parsed_artefact(tmp_path, "pypdf", result)
    assert path == tmp_path / "parsed_pypdf.json"
    assert path.exists()
    assert not (tmp_path / "parsed_pypdf.tmp").exists()

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["reader"] == "pypdf"
    assert [doc["file"] for doc in loaded["parsed_documents"]] == [
        "doc1_climate.pdf",
        "doc2_quantum.pdf",
    ]
    assert loaded["artefact_sha256"] == result["artefact_sha256"]


def test_run_cell_requests_diagnostics_and_persists_retrieval_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require diagnostic IDs for Qrels scoring in the evaluation harness."""
    from rag_mcp.core import retrieval

    calls: list[dict[str, object]] = []

    def fake_search(**kwargs: object) -> list[dict[str, object]]:
        calls.append(kwargs)
        return [{"id": "qasper-doc-1", "score": 0.9}]

    monkeypatch.setattr(retrieval, "search", fake_search)
    monkeypatch.setattr(
        run_eval,
        "_resolve_cell_runtime",
        lambda reader, rerank: (object(), "qasper-test"),
    )

    result = run_eval._run_cell(
        {"name": "pypdf_off", "reader": "pypdf", "rerank": False},
        [{"id": "query-1", "text": "What is the finding?"}],
        {"query-1": {"qasper-doc-1": 1}},
        [1],
    )

    assert calls[0]["include_diagnostics"] is True
    assert result["per_query"][0]["retrieved"] == [{"id": "qasper-doc-1", "score": 0.9}]
    assert result["metrics"]["hit@1"] == 1.0


# ---------------------------------------------------------------------------
# Task 6.3.3 parse-stage artefact metrics: every parsed record must expose
# a source-PDF page count and a token count, each distinct from the
# emitted-document count, including the zero-token contract for failed
# parses (empty text has a computable token count of zero).
# ---------------------------------------------------------------------------


class _StubAdapter:
    """Deterministic stand-in for a production PDF reader adapter.

    Both fixtures are single-page and pypdf emits one document per page,
    so a real parse cannot separate "source-PDF pages" from "emitted
    documents".  A stub with a controlled emitted-document list can.
    """

    def __init__(self, texts: list[str]) -> None:
        self._texts = texts

    def load_data(self, pdf_path: Path) -> list[SimpleNamespace]:
        return [SimpleNamespace(text=text) for text in self._texts]


class _RaisingAdapter:
    """Adapter whose load_data always fails (failure-path contract)."""

    def load_data(self, pdf_path: Path) -> list[SimpleNamespace]:
        raise RuntimeError("stub parse failure")


def _true_source_page_count(pdf_path: Path) -> int:
    """Measure the source-PDF page count independently of the harness."""
    from pypdf import PdfReader

    return len(PdfReader(str(pdf_path)).pages)


def test_parsed_records_expose_source_page_count() -> None:
    """Each record's page_count equals the source-PDF page count.

    Measured independently with pypdf over the frozen fixture PDFs.
    """
    result = exp14.parse_corpus(FIXTURES_DIR, "pypdf")
    for doc in result["parsed_documents"]:
        assert doc["error"] is None
        expected = _true_source_page_count(FIXTURES_DIR / doc["file"])
        assert isinstance(doc["source_page_count"], int)
        assert doc["source_page_count"] == expected


def test_source_page_count_distinct_from_emitted_document_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """source_page_count must measure the source PDF, not len(documents).

    A stub emitting two documents for the single-page fixture must not
    change the recorded page count away from the true source page count,
    and the emission itself must be recorded in its own field.
    """
    from rag_mcp.integrations.pdf import factory as pdf_factory

    real = exp14.parse_corpus(FIXTURES_DIR, "pypdf")
    stub = _StubAdapter([real["parsed_documents"][0]["text"], ""])

    monkeypatch.setattr(pdf_factory, "get_pdf_reader", lambda reader: stub)
    result = exp14.parse_corpus(FIXTURES_DIR, "pypdf")

    doc1 = result["parsed_documents"][0]
    assert doc1["file"] == "doc1_climate.pdf"
    assert doc1["error"] is None
    # doc1_climate.pdf has exactly one source page; the stub emitted two
    # documents.  The record must report the page count, not the emission.
    assert _true_source_page_count(FIXTURES_DIR / doc1["file"]) == 1
    assert doc1["source_page_count"] == 1
    assert doc1["emitted_document_count"] == 2


def test_parsed_records_expose_token_count() -> None:
    """Each record exposes a token count derived from its text.

    The bound 0 < token_count < char_count holds for any sane
    tokenisation of the fixture texts (118/110 chars, 16/12 words) and
    rules out copies of char_count or zero-filled placeholders.
    """
    result = exp14.parse_corpus(FIXTURES_DIR, "pypdf")
    for doc in result["parsed_documents"]:
        assert doc["error"] is None
        assert isinstance(doc["token_count"], int)
        assert 0 < doc["token_count"] < doc["char_count"]


def test_token_count_is_not_emitted_document_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """token_count must track the text, not the emitted-document count.

    Under a stub emitting two documents (one non-empty, one empty) the
    token count must remain a positive text-derived number distinct
    from the emitted-document count of two.
    """
    from rag_mcp.integrations.pdf import factory as pdf_factory

    real = exp14.parse_corpus(FIXTURES_DIR, "pypdf")
    stub = _StubAdapter([real["parsed_documents"][0]["text"], ""])

    monkeypatch.setattr(pdf_factory, "get_pdf_reader", lambda reader: stub)
    result = exp14.parse_corpus(FIXTURES_DIR, "pypdf")

    doc1 = result["parsed_documents"][0]
    assert doc1["error"] is None
    assert doc1["emitted_document_count"] == 2
    assert doc1["token_count"] != doc1["emitted_document_count"]
    assert doc1["token_count"] > 0


def test_parse_failure_records_zero_tokens_and_unknown_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed parses record the metrics they can know.

    A parse failure has empty text, so its token count is zero; the
    source page count is unknowable without parsing, so it stays None.
    """
    from rag_mcp.integrations.pdf import factory as pdf_factory

    monkeypatch.setattr(pdf_factory, "get_pdf_reader", lambda reader: _RaisingAdapter())
    result = exp14.parse_corpus(FIXTURES_DIR, "pypdf")

    for doc in result["parsed_documents"]:
        assert doc["error"] is not None
        assert doc["text"] == ""
        assert doc["char_count"] == 0
        # Empty text has a computable token count: zero, not None
        # (mirroring char_count, which is recorded as 0, not None).
        assert doc["token_count"] == 0
        # The source page count is unknowable without a successful parse.
        assert doc["source_page_count"] is None
