"""Graph adapters forward the run's own store and settings (task 3.8).

The default-accessor scan in ``tests/test_no_global_settings_reads.py``
catches a read of a process default. It cannot catch an adapter that
silently passes ``store=None``: the metadata layer then falls back to seed
categories without reading any default. These behavioural tests spy on
the call that receives the store, so dropping it fails a test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.ingestion.snapshot import copy_sources, pin_detection
from tests.unit.test_ingestion_graph_adapters_support import (
    admit,
    build_catalogue,
    canonical_graph,
    offline_settings,
    resources,
    run_by_hand,
)

from omrg.core.metadata import extractor


class _MarkedStore:
    """Wrap the real store so the test can recognise it by identity."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@pytest.mark.asyncio
async def test_enrich_forwards_run_store_and_settings_to_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """Every unit's metadata call receives the run's store and node settings."""
    from omrg.core.vectordb import get_default_store

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = offline_settings(effective_settings)
    store = _MarkedStore(get_default_store())
    catalogue = build_catalogue()
    snapshot = admit(canonical_graph("graph_forwarding"), settings, root, catalogue)

    seen: list[tuple[Any, Any]] = []
    real = extractor.extract_metadata_with_status_async

    async def _spy(text: str, name: str, call_settings: Any, *, store: Any = None) -> Any:
        seen.append((store, call_settings))
        return await real(text, name, call_settings, store=store)

    monkeypatch.setattr(extractor, "extract_metadata_with_status_async", _spy)

    outputs = await run_by_hand(snapshot, catalogue, resources(snapshot, catalogue, store))

    assert outputs, "the parity sources produced no units"
    assert seen, "prepare.enrich never reached the metadata extractor"
    assert all(call_store is store for call_store, _ in seen)
    assert all(call_settings is snapshot.node("enrich").settings for _, call_settings in seen)
