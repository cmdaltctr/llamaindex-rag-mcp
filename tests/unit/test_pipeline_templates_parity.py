"""Canonical answer and ingestion templates equal Engine operations (task 4.5).

Answer: each of the 18 recorded answer cases runs twice on Engines over the
same in-memory store, once through ``Engine.answer`` and once through the
answer template with ``Engine.run_pipeline``. Both paths retrieve the
case rows from the store, use the same scripted answer and judge seams,
and must give the same result, keys and model-call counts.

Ingestion: the ingestion template is the graph that
``canonical_ingestion_definition`` returns, and it writes the same rows
as ``Engine.ingest`` on the recorded ingestion fixtures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from tests.fixtures.pipeline_parity.answer.harness import (
    CASE_NAMES,
    QUERY,
    case_by_name,
    case_rows,
    case_settings,
    make_seam,
    observation,
)
from tests.fixtures.pipeline_parity.ingestion.snapshot import (
    collect_rows,
    copy_sources,
    pin_detection,
)
from tests.unit.test_answer_graph_adapters_support import UNKNOWN_PROVIDER, FakeLLM
from tests.unit.test_engine_pipelines_support import Factory, FakeStore, build_engine
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrg.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrg.core.pipelines import RunStatus
from omrg.core.vectordb.lancedb.store import LanceVectorStore
from omrg.engine import Engine
from omrg.pipeline_templates import answer_template, ingestion_template

_COLLECTION = "parity"


def _store_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn ``search()``-shaped fixture rows into store rows with lineage."""
    return [
        {
            "id": row["chunk_id"],
            "text": row["text"],
            "dense_score": row["score"],
            "metadata": {
                "file_name": row["source"],
                "source_id": row["source_id"],
                "source_version": row["source_version"],
                "chunk_id": row["chunk_id"],
                "source_chunk_index": row["source_chunk_index"],
                "source_chunk_count": 1,
            },
        }
        for row in rows
    ]


def _engine(case: dict[str, Any], settings: Any) -> tuple[Engine, Any, Any]:
    """Return an Engine over the case rows, with fresh scripted seams."""
    complete, judge = make_seam(case.get("complete")), make_seam(case.get("judge"))
    answer_factory = Factory(FakeLLM(complete) if complete else None)
    judge_factory = Factory(FakeLLM(judge) if judge else None)
    if case.get("verify_unavailable_reason"):
        judge_factory = Factory(error=ValueError(UNKNOWN_PROVIDER))
    engine = build_engine(
        settings,
        FakeStore(_store_rows(case_rows(case))),
        answer_llm_factory=answer_factory,
        verify_llm_factory=judge_factory,
    )
    return engine, complete, judge


@pytest.mark.parametrize("name", CASE_NAMES)
async def test_answer_template_matches_engine_answer(name: str, effective_settings: Any) -> None:
    """Statuses, citations, verification markers and model calls equal ``Engine.answer``."""
    case = case_by_name(name)
    settings = case_settings(effective_settings(), case)

    engine, complete, judge = _engine(case, settings)
    standard = await engine.answer(QUERY, collection_name=_COLLECTION, include_diagnostics=True)
    want = observation(standard, complete, judge)

    engine, complete, judge = _engine(case, settings)
    data = answer_template(_COLLECTION, rerank=False).model_dump(mode="json")
    synthesise = next(n for n in data["graph"]["nodes"] if n["id"] == "synthesise")
    synthesise["params"] = {"include_diagnostics": True}
    result = await engine.run_pipeline(data, inputs={"query": QUERY})

    assert result.status is RunStatus.SUCCEEDED, result.error
    got = observation(dict(result.outputs["answer"]), complete, judge)
    assert got == want


def test_answer_parity_covers_all_eighteen_cases() -> None:
    """The template parity run covers every recorded answer case."""
    assert len(CASE_NAMES) == 18


# ── Ingestion ─────────────────────────────────────────────────────────


def test_ingestion_template_is_the_canonical_ingestion_graph() -> None:
    """One description: the template and the fingerprint source are equal."""
    for collection in (None, "notes"):
        template = ingestion_template(collection)
        assert template == canonical_ingestion_definition(collection)


async def test_ingestion_template_writes_the_same_rows_as_engine_ingest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """Stored chunks and source identities equal ``Engine.ingest``."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    engine = Engine(
        offline_settings(effective_settings),
        store=store,
        embed_model=LlamaIndexSettings.embed_model,
    )
    standard = await engine.ingest(str(root), collection_name="standard")

    result = await engine.run_pipeline(ingestion_template("graph"), inputs={"path": str(root)})

    assert result.status is RunStatus.SUCCEEDED, result.error
    assert len(result.completed_effects) == standard["files_indexed"] == 3
    assert [set(unit.outputs) for unit in result.units] == [{"summary"}] * 3
    graph_rows = collect_rows(engine._store, "graph", root)
    assert graph_rows and graph_rows == collect_rows(engine._store, "standard", root)
    engine.close()
