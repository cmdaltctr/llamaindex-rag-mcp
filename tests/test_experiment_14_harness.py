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
from types import ModuleType

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
        assert doc["page_count"] is None or isinstance(doc["page_count"], int)
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
    assert manifest["protocol_version"] == "2.0"
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
    assert len(build_cells) == 2
    # A plan restricted to the generator's cells must accept exactly those
    # cells (this also validates factor names/levels against the declared
    # manipulated factors).
    build_only = ExperimentPlan.from_dict({**payload, "cells": build_cells})
    build_only.assert_runner_cells(build_cells)

    eval_cells = run_eval.build_eval_cell_matrix()
    assert len(eval_cells) == 4
    eval_only = ExperimentPlan.from_dict({**payload, "cells": eval_cells})
    eval_only.assert_runner_cells(eval_cells)

    # The full plan declares exactly the union of both pure generators.
    plan_by_id = {cell.id: dict(cell.factors) for cell in plan.cells}
    generated_by_id = {cell["id"]: cell["factors"] for cell in [*build_cells, *eval_cells]}
    assert plan_by_id == generated_by_id
    assert set(plan_by_id) == {
        "build_pypdf",
        "build_liteparse",
        "pypdf_off",
        "pypdf_on",
        "liteparse_off",
        "liteparse_on",
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
