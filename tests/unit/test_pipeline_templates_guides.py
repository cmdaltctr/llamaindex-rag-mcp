"""The guides touched by tasks 3.7 and 4.6 describe the real code.

Checks, for the pipeline, library, ingestion, retrieval (reranker) and
architecture guides:

* every ``src/omrg/...`` path they name exists;
* every function named in a "stages as graph operations" table exists in
  the module that the same row names, and the row's graph operation is in
  the Engine catalogue;
* the defaults the guides say are unchanged equal the code defaults;
* the documented ``search()`` row keys equal the keys recorded before the
  change, and the documented ingest keys equal the keys ``ingest`` returns.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml
from tests.fixtures.pipeline_parity.retrieval import harness

from omrg.compose_pipelines import build_operation_catalogue
from omrg.core.chunking.settings import ChunkingSettings
from omrg.core.retrieval.policy import _effective_threshold
from omrg.core.retrieval.settings import RetrievalSettings

_ROOT = Path(__file__).resolve().parents[2]
_GUIDES = _ROOT / "docs" / "guides"
TOUCHED = ("pipelines.md", "library-usage.md", "ingestion.md", "reranker.md", "architecture.md")
_STAGE_TABLES = ("ingestion.md", "reranker.md")
_SRC_PATH = re.compile(r"src/omrg/[\w./-]+\.py")
_TICKED = re.compile(r"`([^`]+)`")


def _text(name: str) -> str:
    return (_GUIDES / name).read_text(encoding="utf-8")


def _stage_rows(name: str) -> list[tuple[list[str], list[str], str]]:
    """Return ``(functions, modules, operation)`` for each stage-table row."""
    text = _text(name)
    start = text.index("| Stage | Shared function | Module | Graph operation |")
    rows = []
    for line in text[start:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        _stage, functions, modules, operation = (c.strip() for c in line.strip("|").split("|"))
        names = [n for n in _TICKED.findall(functions.split("(")[0]) if n.isidentifier()]
        rows.append((names, _TICKED.findall(modules), _TICKED.findall(operation)[0]))
    return rows


def _defined_names(module_path: str) -> set[str]:
    tree = ast.parse((_ROOT / module_path).read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


@pytest.mark.parametrize("name", TOUCHED)
def test_every_named_source_path_exists(name: str) -> None:
    """A guide that names a moved or missing file fails here."""
    missing = sorted({p for p in _SRC_PATH.findall(_text(name)) if not (_ROOT / p).is_file()})
    assert missing == []


@pytest.mark.parametrize("name", _STAGE_TABLES)
def test_stage_tables_name_real_functions_and_operations(name: str) -> None:
    """Each named function is defined in a named module; each operation is registered."""
    operations = {d.operation_id for d in build_operation_catalogue().descriptors()}
    rows = _stage_rows(name)
    assert len(rows) >= 8
    for functions, modules, operation in rows:
        assert operation in operations, operation
        defined = set().union(*(_defined_names(m) for m in modules))
        assert [f for f in functions if f not in defined] == [], (functions, modules)


def test_documented_defaults_equal_code_defaults() -> None:
    """``top_k=10``, ``chunk_overlap=100``, ``chunk_size=512``, rerank off, ÷30 transform."""
    retrieval, chunking = RetrievalSettings(), ChunkingSettings()
    assert (retrieval.top_k, retrieval.rerank_enabled) == (10, False)
    assert (chunking.chunk_size, chunking.chunk_overlap) == (512, 100)
    profiles = _ROOT / "src" / "omrg" / "config" / "profiles"
    documents = yaml.safe_load((profiles / "documents.yaml").read_text(encoding="utf-8"))
    codebase = yaml.safe_load((profiles / "codebase.yaml").read_text(encoding="utf-8"))
    assert documents["retrieval"]["rerank_enabled"] is True
    assert codebase["retrieval"]["rerank_enabled"] is False
    assert _effective_threshold(0.3, rerank=True) == pytest.approx(0.01)
    assert _effective_threshold(0.3, rerank=False) == 0.3
    reranker = _text("reranker.md")
    assert "`retrieval.top_k` defaults to `10`" in reranker
    assert "`retrieval.rerank_enabled` defaults to `false`" in reranker
    assert "divided by 30" in reranker
    ingestion = _text("ingestion.md")
    assert "`chunking.chunk_size` defaults to `512`" in ingestion
    assert "`chunking.chunk_overlap` defaults to `100`" in ingestion


def documented_ingest_keys() -> set[str]:
    """Return the ingest result keys the ingestion guide lists."""
    line = next(
        line for line in _text("ingestion.md").splitlines() if "same dictionary keys" in line
    )
    return set(_TICKED.findall(line.split("as before:", 1)[1]))


def test_documented_ingest_keys_match_the_ingest_result_builder() -> None:
    """The listed keys are the keys ``ingest_path_async`` builds."""
    source = (_ROOT / "src/omrg/core/ingestion/pipeline.py").read_text(encoding="utf-8")
    built = set(re.findall(r'^\s+"(\w+)": ', source[source.index("common = {") :], re.M))
    built |= {"status", "error_type", "message", "warnings"}
    assert documented_ingest_keys() == built


def test_search_rows_keep_the_recorded_public_keys(monkeypatch, effective_settings) -> None:
    """``search()`` rows have the key set recorded before the graph work."""
    case = next(c for c in harness.load_cases() if c["name"] == "public_shape_hybrid")
    rows = harness.run_search(
        case, harness.load_corpus(), monkeypatch=monkeypatch, settings_factory=effective_settings
    )
    assert harness.public_keys(rows) == case["expected"]["keys"]
