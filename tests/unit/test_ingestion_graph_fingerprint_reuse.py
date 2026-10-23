"""Graph shape in the source index identity: reuse versus reprocess (task 3.5).

The standard path and the canonical graph write the same
``source_index_identity``. A changed index-shaping operation makes every
affected source reprocess on its next explicit ingest. A layout or node-id
change keeps reuse. Admitting or saving a changed graph alone does not
change stored rows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.ingestion.snapshot import (
    collect_rows,
    copy_sources,
    pin_detection,
)
from tests.unit.test_ingestion_graph_adapters_support import (
    admit,
    build_catalogue,
    canonical_graph,
    offline_settings,
    resources,
    run_by_hand,
)
from tests.unit.test_ingestion_graph_fingerprint import _rename

from omrs.core.ingestion import pipeline
from omrs.core.ingestion.graph_fingerprint import SHAPE_SCHEMA, graph_shape, ingestion_shape
from omrs.core.ingestion.source_state import build_index_identity
from omrs.core.pipelines import parse_definition


def test_standard_identity_digest_is_unchanged(effective_settings: Any) -> None:
    """No graph shape keeps the schema-6 digest; a shape block changes it."""
    settings = effective_settings()
    kwargs = {"content_type": "document/markdown", "chunk_size": 512, "chunk_overlap": 64}
    plain = build_index_identity(settings, **kwargs)
    assert build_index_identity(settings, graph_shape=None, **kwargs) == plain
    shaped = build_index_identity(
        settings, graph_shape={"schema": SHAPE_SCHEMA, "fingerprint": "f" * 64}, **kwargs
    )
    assert shaped != plain


async def _standard(root: Path, settings: Any, store: Any, collection: str) -> dict:
    return await pipeline.ingest_path_async(
        str(root), collection_name=collection, effective_settings=settings, store=store
    )


async def _graph(data: dict, root: Path, settings: Any, store: Any) -> list[dict]:
    catalogue = build_catalogue()
    snapshot = admit(data, settings, root, catalogue)
    outputs = await run_by_hand(snapshot, catalogue, resources(snapshot, catalogue, store))
    return [o.values["summary"] for o in outputs]


@pytest.fixture
def ingest_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any):
    from omrs.core.vectordb import get_default_store

    pin_detection(monkeypatch)
    return copy_sources(tmp_path), offline_settings(effective_settings), get_default_store()


@pytest.mark.asyncio
async def test_layout_and_id_changes_reuse_standard_sources(ingest_env: Any) -> None:
    """A presentation-only change of the canonical graph skips every source."""
    root, settings, store = ingest_env
    await _standard(root, settings, store, "shape_layout")
    before = collect_rows(store, "shape_layout", root)
    data = _rename(canonical_graph("shape_layout"), {"read": "reader", "chunk": "split_1"})
    data["layout"] = {"title": "Moved", "positions": {"reader": {"x": 40, "y": 8}}}

    summaries = await _graph(data, root, settings, store)

    assert [s["status"] for s in summaries] == ["skipped_unchanged"] * 3
    assert collect_rows(store, "shape_layout", root) == before


@pytest.mark.asyncio
async def test_changed_shaping_operation_reprocesses_then_reuses(ingest_env: Any) -> None:
    """A changed chunk parameter rebuilds each source once, then reuses it."""
    root, settings, store = ingest_env
    await _standard(root, settings, store, "shape_change")
    before = collect_rows(store, "shape_change", root)
    data = canonical_graph("shape_change", chunk={"chunk_size": 512, "chunk_overlap": 20})

    first = await _graph(data, root, settings, store)
    after = collect_rows(store, "shape_change", root)
    second = await _graph(data, root, settings, store)

    assert [s["status"] for s in first] == ["indexed"] * 3
    old_identities = {r["metadata"]["source_index_identity"] for r in before}
    new_identities = {r["metadata"]["source_index_identity"] for r in after}
    assert old_identities.isdisjoint(new_identities)
    assert [s["status"] for s in second] == ["skipped_unchanged"] * 3


@pytest.mark.asyncio
async def test_shape_change_without_parameter_effect_still_reprocesses(ingest_env: Any) -> None:
    """A changed connection reprocesses, even when the chunks would match."""
    root, settings, store = ingest_env
    await _standard(root, settings, store, "shape_connection")
    from tests.unit.test_ingestion_graph_fingerprint import _bypass_normalise

    summaries = await _graph(
        _bypass_normalise(canonical_graph("shape_connection")), root, settings, store
    )

    assert [s["status"] for s in summaries] == ["indexed"] * 3


@pytest.mark.asyncio
async def test_admitting_a_changed_graph_does_not_change_vectors(ingest_env: Any) -> None:
    """Saving or admitting a graph computes a shape and writes nothing."""
    root, settings, store = ingest_env
    await _standard(root, settings, store, "shape_saved")
    before = collect_rows(store, "shape_saved", root)
    catalogue = build_catalogue()
    data = canonical_graph("shape_saved", chunk={"chunk_size": 512, "chunk_overlap": 20})

    snapshot = admit(data, settings, root, catalogue)
    shape = ingestion_shape(snapshot, catalogue)

    assert not shape.standard
    assert shape == graph_shape(parse_definition(data).graph, catalogue)
    assert collect_rows(store, "shape_saved", root) == before
