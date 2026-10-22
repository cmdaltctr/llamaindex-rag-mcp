"""Public result fields through ``Engine.run_pipeline`` (verification gap B).

The runner tests prove ``skipped_nodes`` and ``completed_effects`` on the
runner alone. These tests read the same fields from the public
``PipelineResult`` that ``Engine.run_pipeline`` returns, for a run that
fails part way and for a run that is cancelled part way.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from tests.fixtures.pipeline_parity.ingestion.snapshot import copy_sources, pin_detection
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrs.core.ingestion import graph_adapters
from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrs.core.pipelines import NodeStatus, PipelineResult, RunCancellation, RunStatus
from omrs.core.vectordb.lancedb.store import LanceVectorStore
from omrs.engine import Engine

_FAILING_SOURCE = "notes.txt"


def _engine(tmp_path: Path, settings: Any) -> Engine:
    """Return an Engine over a temporary LanceDB store and the mock embedder."""
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    return Engine(settings, store=store, embed_model=LlamaIndexSettings.embed_model)


def _break_splitter_for(monkeypatch: pytest.MonkeyPatch, file_name: str) -> None:
    """Make ``prepare.chunk`` fail for one source only."""
    real = graph_adapters.split_documents

    async def _split(documents: list, file_path: Path, **kwargs: Any) -> list:
        if Path(file_path).name == file_name:
            raise RuntimeError("splitter broke")
        return await real(documents, file_path, **kwargs)

    monkeypatch.setattr(graph_adapters, "split_documents", _split)


async def test_failed_run_reports_skipped_nodes_and_completed_effects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """A failing node names its skipped dependants; earlier commits stay listed."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    _break_splitter_for(monkeypatch, _FAILING_SOURCE)
    engine = _engine(tmp_path, offline_settings(effective_settings))

    result = await engine.run_pipeline(
        canonical_ingestion_definition("public_fail"), inputs={"path": str(root)}
    )

    assert isinstance(result, PipelineResult)
    assert result.status is RunStatus.FAILED
    assert result.failed_node == "chunk"
    assert result.error and "splitter broke" in result.error
    assert result.skipped_nodes == ("embed", "commit")
    committed = {u.unit_id: u.effects for u in result.units if u.status is NodeStatus.SUCCEEDED}
    assert sorted(committed) == ["guide.md", "nested/appendix.md"]
    assert result.completed_effects == tuple(e for u in result.units for e in u.effects)
    assert len(result.completed_effects) == 2
    assert all(e.startswith("committed:src_") for e in result.completed_effects)
    failed = next(u for u in result.units if u.unit_id == _FAILING_SOURCE)
    assert (failed.status, failed.failed_node, failed.effects) == (NodeStatus.FAILED, "chunk", ())
    engine.close()


async def test_cancelled_run_keeps_the_effect_that_finished_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """Cancellation after the first commit keeps that commit in the result."""
    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    engine = _engine(tmp_path, offline_settings(effective_settings))
    token = RunCancellation()

    async def _cancel_after_first_commit(event: Any) -> None:
        if event.kind == "effect_committed":
            token.cancel("user request")

    result = await engine.run_pipeline(
        canonical_ingestion_definition("public_cancel"),
        inputs={"path": str(root)},
        on_event=_cancel_after_first_commit,
        cancellation=token,
    )

    assert result.status is RunStatus.CANCELLED
    assert result.failed_node is None
    assert len(result.completed_effects) == 1
    first = result.units[0]
    assert first.status is NodeStatus.SUCCEEDED
    assert result.completed_effects == first.effects
    assert [u.status for u in result.units[1:]] == [NodeStatus.CANCELLED] * 2
    engine.close()
